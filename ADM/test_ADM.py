"""
Tests for the Inventive Step ADMs and ADM_Construction module.

Many of these tests were created with the assistance of Gemini Pro 3 and evaluated manually for errors
"""

import unittest
from unittest.mock import MagicMock, patch, ANY
import sys
import io
import logging
from contextlib import redirect_stdout

# Import the module to be tested
from ADM_Construction import ADM, Node, SubADMNode, EvaluationNode, GatedBLF
from inventive_step_ADM import adm_initial, adm_main, sub_adm_1, sub_adm_2

# Configure logging to capture output during tests if needed, 
# or suppress it to keep test output clean.
logging.basicConfig(level=logging.CRITICAL)

class TestNode(unittest.TestCase):
    """Tests for the base Node class functionality"""

    def test_node_initialization_basic(self):
        """Test basic node initialization with no logic"""
        node = Node("TestNode")
        self.assertEqual(node.name, "TestNode")
        self.assertEqual(node.acceptance, None)
        self.assertEqual(node.children, None)
        self.assertEqual(node.statement, None)

    def test_node_initialization_with_logic(self):
        """Test node initialization with infix logic strings"""
        # "A and B" -> Postfix: "A B and"
        node = Node("LogicNode", acceptance=["A and B"], statement=["Success"])
        
        self.assertEqual(len(node.acceptance), 1)
        self.assertEqual(node.acceptance[0], "A B and")
        self.assertIn("A", node.children)
        self.assertIn("B", node.children)
        self.assertEqual(node.statement, ["Success"])

    def test_logic_converter(self):
        """Test the infix-to-postfix conversion logic"""
        node = Node("Converter")
        
        # Test 1: Simple AND
        self.assertEqual(node.logicConverter("A and B"), "A B and")
        
        # Test 2: OR
        self.assertEqual(node.logicConverter("A or B"), "A B or")
        
        # Test 3: NOT
        self.assertEqual(node.logicConverter("not A"), "A not")
        
        # Test 4: Reject
        self.assertEqual(node.logicConverter("reject A"), "A reject")
        
        # Test 5: Complex Parentheses
        # (A or B) and C -> A B or C and
        self.assertEqual(node.logicConverter("( A or B ) and C"), "A B or C and")
        
        # Test 6: Operator Precedence (AND before OR)
        # A or B and C -> A B C and or
        self.assertEqual(node.logicConverter("A or B and C"), "A B C and or")

class TestADMLogic(unittest.TestCase):
    """Tests for the ADM Logic Engine (EvaluateNode, 3VL, Postfix)"""

    def setUp(self):
        self.adm = ADM("LogicTestADM")
        # Setup a simple graph: Root <- A, B
        self.adm.addNodes("A")
        self.adm.addNodes("B")
        self.adm.addNodes("Root", acceptance=["A and B"])
        self.adm.root_node = self.adm.nodes["Root"]

    def test_postfix_evaluation_standard(self):
        """Test standard boolean evaluation of postfix strings"""
        # Case 1: A=True, B=True -> True
        self.adm.case = ["A", "B"]
        result = self.adm.postfixEvaluation("A B and", mode='standard')
        self.assertTrue(result)

        # Case 2: A=True, B=False -> False
        self.adm.case = ["A"]
        result = self.adm.postfixEvaluation("A B and", mode='standard')
        self.assertFalse(result)

        # Case 3: NOT operator
        self.adm.case = []
        result = self.adm.postfixEvaluation("A not", mode='standard')
        self.assertTrue(result) # Not False -> True

    def test_postfix_evaluation_reject_operator(self):
        """Test the 'reject' operator side effects"""
        self.adm.case = ["A"]
        
        # "reject A" -> If A is present, self.reject should be True
        self.adm.reject = False
        res = self.adm.postfixEvaluation("A reject", mode='standard')
        self.assertTrue(self.adm.reject)
        self.assertTrue(res) # The value itself remains True on stack

        # "reject B" -> If B is absent, self.reject should be False
        self.adm.reject = False
        res = self.adm.postfixEvaluation("B reject", mode='standard')
        self.assertFalse(self.adm.reject)
        self.assertFalse(res)

    def test_check_condition_3vl(self):
        """Test 3VL"""
        # OR Logic
        self.assertTrue(self.adm.checkCondition("or", True, None))   # T or U = T
        self.assertIsNone(self.adm.checkCondition("or", False, None)) # F or U = U
        self.assertIsNone(self.adm.checkCondition("or", None, None))  # U or U = U
        
        # AND Logic
        self.assertIsNone(self.adm.checkCondition("and", True, None)) # T and U = U
        self.assertFalse(self.adm.checkCondition("and", False, None)) # F and U = F
        
        # NOT Logic
        self.assertIsNone(self.adm.checkCondition("not", None)) # not U = U

    def test_evaluate_node_standard(self):
        """Test evaluateNode in standard mode"""
        self.adm.case = ["A", "B"]
        val, idx = self.adm.evaluateNode(self.adm.nodes["Root"], mode='standard')
        self.assertTrue(val)

        self.adm.case = ["A"]
        val, idx = self.adm.evaluateNode(self.adm.nodes["Root"], mode='standard')
        self.assertFalse(val)

    def test_evaluate_node_standard_reject(self):
        """Test evaluateNode with rejection logic"""
        # Root accepts if A is present, but REJECTS if B is present
        # Logic: "A" (index 0), "reject B" (index 1 - implicitly checking logic flow)
        # Actually usually written as "A" in one condition.
        # Let's verify "reject B" works as a blocker.
        
        self.adm.addNodes("RejectRoot", acceptance=["reject B", "A"])
        node = self.adm.nodes["RejectRoot"]

        # Case 1: B present -> Should Reject
        self.adm.case = ["B", "A"]
        val, idx = self.adm.evaluateNode(node, mode='standard')
        print('Value = ', val)
        self.assertFalse(val) 
        # Index should point to the condition that triggered reject (0)
        self.assertEqual(idx, 0)
        
        # Case 2: B absent, A present -> Should Accept
        self.adm.case = ["A"]
        val, idx = self.adm.evaluateNode(node, mode='standard')
        self.assertTrue(val)
        self.assertEqual(idx, 1)

    def test_evaluate_node_3vl_asymmetric(self):
        """Test 3VL Asymmetric Safety (The 'Unknown' handling)"""
        # Node depends on C. C is not in case, not in evaluated_nodes -> Unknown.
        self.adm.addNodes("C")
        self.adm.addNodes("UnkRoot", acceptance=["C"])
        
        node = self.adm.nodes["UnkRoot"]
        self.adm.case = []
        
        # 1. Unknown Positive
        # "C" is Unknown. Positive path exists but is unknown. Result -> Unknown.
        val, _ = self.adm.evaluateNode(node, mode='3vl')
        self.assertIsNone(val)

        # 2. Unknown Reject (Safety Blocker)
        # "A" (True) but "reject C" (Unknown)
        self.adm.addNodes("SafetyRoot", acceptance=["reject C", "A"])
        self.adm.case = ["A"] # A is known True
        
        node_safe = self.adm.nodes["SafetyRoot"]
        val, _ = self.adm.evaluateNode(node_safe, mode='3vl')
        # Even though A is True, C is Unknown. We cannot safely accept.
        self.assertIsNone(val)

        # 3. Proven False
        # "A" (True) AND "C" (Unknown). 
        # Actually "A and C". T and U = U.
        self.adm.addNodes("AndRoot", acceptance=["A and C"])
        val, _ = self.adm.evaluateNode(self.adm.nodes["AndRoot"], mode='3vl')
        self.assertIsNone(val)
        
        # 4. Proven False (Asymmetric Logic)
        # Scenario: "reject C" (Unknown) and "A" (Known False)
        # Logic: We have a "Defeater" that is Unknown, but the only "Enabler" (A) is definitely False.
        # Since there is no way to Accept (A is False), the Unknown status of C doesn't matter.
        # The node should be definitively False.
        
        self.adm.addNodes("FalseRoot", acceptance=["reject C", "A"])
        
        # A is evaluated (False), C is unevaluated (Unknown)
        self.adm.case = [] 
        self.adm.evaluated_nodes = {"A"} 
        
        val, _ = self.adm.evaluateNode(self.adm.nodes["FalseRoot"], mode='3vl')
        
        # Assert False (not None) because the positive path is dead
        self.assertFalse(val)
        self.assertIsNotNone(val)
        
    #========== MORE LOGIC TESTS FOR 3VL ========
    
    def test_scen1_A_rejectB_B_True_A_Unknown(self):
        """
        Scenario: Acceptance ["A", "reject B"]
        State: B is True, A is Unknown.
        Logic: Strict ordering checks A first. A is Unknown.
        Outcome: UNKNOWN (Cannot early stop).
        """
        self.adm.addNodes("B")
        self.adm.addNodes("A")
        self.adm.addNodes("Root", acceptance=["A", "reject B"], root=True)
        self.adm.root_node = self.adm.nodes["Root"]

        # Case: B is present (True), A is unevaluated (Unknown)
        self.adm.case = ["B"]
        evaluated_nodes = {"B"}

        result = self.adm.check_early_stop(evaluated_nodes)
        self.assertFalse(result)

    def test_scen2_A_rejectB_B_False_A_Unknown(self):
        """
        Scenario: Acceptance ["A", "reject B"]
        State: B is False, A is Unknown.
        Logic: Strict ordering checks A first. A is Unknown.
        Outcome: UNKNOWN (Cannot early stop).
        """
        self.adm.addNodes("B")
        self.adm.addNodes("A")
        self.adm.addNodes("Root", acceptance=["A", "reject B"], root=True)
        self.adm.root_node = self.adm.nodes["Root"]

        # Case: Empty (B is False), A is unevaluated (Unknown)
        self.adm.case = []
        evaluated_nodes = {"B"} # B has been evaluated as False

        result = self.adm.check_early_stop(evaluated_nodes)
        self.assertFalse(result)

    def test_scen3_rejectA_B_B_True_A_Unknown(self):
        """
        Scenario: Acceptance ["reject A", "B"]
        State: B is True, A is Unknown.
        Logic: Strict ordering checks 'reject A' first. A is Unknown.
        Outcome: UNKNOWN (Cannot early stop - A might reject).
        """
        self.adm.addNodes("A")
        self.adm.addNodes("B")
        self.adm.addNodes("Root", acceptance=["reject A", "B"], root=True)
        self.adm.root_node = self.adm.nodes["Root"]

        # Case: B is present (True), A is unevaluated (Unknown)
        self.adm.case = ["B"]
        evaluated_nodes = {"B"}

        result = self.adm.check_early_stop(evaluated_nodes)
        self.assertFalse(result)

    def test_scen4_rejectA_B_B_False_A_Unknown(self):
        """
        Scenario: Acceptance ["reject A", "B"]
        State: B is False, A is Unknown.
        Logic: A is Unknown Defeater, B is False Enabler.
               If A triggers -> Reject (False).
               If A doesn't trigger -> B is False -> Default False.
        Outcome: FALSE (Proven False - Can early stop).
        """
        self.adm.addNodes("A")
        self.adm.addNodes("B")
        self.adm.addNodes("Root", acceptance=["reject A", "B"], root=True)
        self.adm.root_node = self.adm.nodes["Root"]

        # Case: Empty (B is False), A is unevaluated (Unknown)
        self.adm.case = []
        evaluated_nodes = {"B"}

        result = self.adm.check_early_stop(evaluated_nodes)
        self.assertTrue(result) 
        # Optional: Assert the node value is False
        val, _ = self.adm.evaluateNode(self.adm.root_node, mode='3vl')
        self.assertFalse(val)

    def test_scen5_A_B_B_True_A_Unknown(self):
        """
        Scenario: Acceptance ["A", "B"]
        State: B is True, A is Unknown.
        Logic: Strict ordering checks A first. A is Unknown.
        Outcome: UNKNOWN (Cannot early stop - A could match first).
        """
        self.adm.addNodes("A")
        self.adm.addNodes("B")
        self.adm.addNodes("Root", acceptance=["A", "B"], root=True)
        self.adm.root_node = self.adm.nodes["Root"]

        # Case: B is present (True), A is unevaluated (Unknown)
        self.adm.case = ["B"]
        evaluated_nodes = {"B"}

        result = self.adm.check_early_stop(evaluated_nodes)
        self.assertFalse(result)

    def test_scen6_A_B_B_False_A_Unknown(self):
        """
        Scenario: Acceptance ["A", "B"]
        State: B is False, A is Unknown.
        Logic: Strict ordering checks A first. A is Unknown.
        Outcome: UNKNOWN (Cannot early stop - A could be True).
        """
        self.adm.addNodes("A")
        self.adm.addNodes("B")
        self.adm.addNodes("Root", acceptance=["A", "B"], root=True)
        self.adm.root_node = self.adm.nodes["Root"]

        # Case: Empty (B is False), A is unevaluated (Unknown)
        self.adm.case = []
        evaluated_nodes = {"B"}

        result = self.adm.check_early_stop(evaluated_nodes)
        self.assertFalse(result)

    def test_scen7_rejectA_rejectB_B_True_A_Unknown(self):
        """
        Scenario: Acceptance ["reject A", "reject B"]
        State: B is True, A is Unknown.
        Logic: A is Unknown Defeater, B is True Defeater.
               If A triggers -> Reject.
               If A doesn't -> B triggers -> Reject.
               Outcome is stable.
        Outcome: FALSE (Proven False - Can early stop).
        """
        self.adm.addNodes("A")
        self.adm.addNodes("B")
        self.adm.addNodes("Root", acceptance=["reject A", "reject B"], root=True)
        self.adm.root_node = self.adm.nodes["Root"]

        # Case: B is present (True), A is unevaluated (Unknown)
        self.adm.case = ["B"]
        evaluated_nodes = {"B"}

        result = self.adm.check_early_stop(evaluated_nodes)
        self.assertTrue(result)
        
        # Verify it resolves to False (Rejected)
        val, _ = self.adm.evaluateNode(self.adm.root_node, mode='3vl')
        self.assertFalse(val)

    def test_scen8_rejectA_rejectB_B_False_A_Unknown(self):
        """
        Scenario: Acceptance ["reject A", "reject B"]
        State: B is False, A is Unknown.
        Logic: A is Unknown Defeater. B is False.
               Logic dictates this should be False (Default), 
               but test expectation is UNKNOWN.
        Outcome: UNKNOWN (Cannot early stop).
        """
        self.adm.addNodes("A")
        self.adm.addNodes("B")
        self.adm.addNodes("Root", acceptance=["reject A", "reject B"], root=True)
        self.adm.root_node = self.adm.nodes["Root"]

        # Case: Empty (B is False), A is unevaluated (Unknown)
        self.adm.case = []
        evaluated_nodes = {"B"}

        result = self.adm.check_early_stop(evaluated_nodes)
        self.assertTrue(result)
        
        # Verify it resolves to False (Rejected)
        val, _ = self.adm.evaluateNode(self.adm.root_node, mode='3vl')
        self.assertFalse(val)
    

class TestADMStructureAndFeatures(unittest.TestCase):
    """Tests for Graph building, Traversals, Early Stop, and Explanation"""

    def setUp(self):
        self.adm = ADM("StructTest")
        # Structure: Root -> Child1 -> Leaf1
        self.adm.addNodes("Leaf1")
        self.adm.addNodes("Child1", acceptance=["Leaf1"], statement=["Child1 Accepted"])
        self.adm.addNodes("Root", acceptance=["Child1"], statement=["Root Accepted"], root=True)

    def test_add_nodes_hierarchy(self):
        """Test that addNodes creates children recursively if they don't exist"""
        self.adm.addNodes("NewRoot", acceptance=["NewChild"])
        self.assertIn("NewChild", self.adm.nodes)
        self.assertIsInstance(self.adm.nodes["NewChild"], Node)

    def test_add_information_question(self):
        """Test adding info questions and facts"""
        # 1. Add Question
        self.adm.addInformationQuestion("INFO_1", "What is X?")
        
        # 2. Verify it WAS automatically added to questionOrder (Original Behavior)
        self.assertIn("INFO_1", self.adm.questionOrder)
        
        # 3. Test Fact Setting/Getting
        self.adm.setFact("INFO_1", "ValueX")
        self.assertEqual(self.adm.getFact("INFO_1"), "ValueX")
        
        # 4. Test Error Raising for Missing Fact (New Requirement)
        # This replaces: self.assertIsNone(self.adm.getFact("NON_EXISTENT"))
        with self.assertRaises(NameError):
            self.adm.getFact("NON_EXISTENT")

    def test_template_resolution_success(self):
        """Test successful regex replacement of all {FACTS}"""
        self.adm.setFact("NAME", "John")
        self.adm.setFact("DAY", "Monday")
        
        q = "Hello {NAME}, is it {DAY}?"
        res = self.adm.resolveQuestionTemplate(q)
        
        self.assertEqual(res, "Hello John, is it Monday?")

    def test_template_resolution_missing_fact(self):
        """Test that a single missing fact raises NameError"""
        self.adm.setFact("NAME", "John")
        # Note: 'DAY' is not set
        q = "Hello {NAME}, is it {DAY}?"
        
        with self.assertRaises(NameError):
            self.adm.resolveQuestionTemplate(q)

    def test_template_resolution_no_vars(self):
        """Test that strings without template variables are returned unchanged"""
        q = "Hello World, no vars here."
        res = self.adm.resolveQuestionTemplate(q)
        self.assertEqual(res, "Hello World, no vars here.")

    def test_evaluate_tree_and_explanation(self):
        """Test the full evaluateTree flow and explanation generation"""
        self.adm.case = ["Leaf1"]
        
        # Run evaluation
        statements = self.adm.evaluateTree(self.adm.case)
        
        # Check case expansion (Leaf1 -> Child1 -> Root)
        self.assertIn("Child1", self.adm.case)
        self.assertIn("Root", self.adm.case)
        
        # Check explanation trace
        # Structure: (depth, statement)
        # Root (0) -> Child1 (1)
        expected = [
            (0, "Root Accepted"),
            (1, "Child1 Accepted")
        ]
        self.assertEqual(statements, expected)

    def test_check_early_stop(self):
        """Test early stopping mechanism using 3VL"""
        # Setup: Root needs A OR B. 
        self.adm.addNodes("A")
        self.adm.addNodes("B")
        self.adm.addNodes("OrRoot", acceptance=["A", "B"], root=True)
        self.adm.root_node = self.adm.nodes["OrRoot"]
        
        # Scenario: A is found. B is unknown.
        # In 3VL, (True OR Unknown) = True. Early stop should trigger.
        self.adm.case = ["A"]
        
        # We simulate that 'A' has been evaluated, but 'B' has not
        evaluated_nodes = {"A"}
        
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            result = self.adm.check_early_stop(evaluated_nodes)
            self.assertTrue(result)
            self.assertIn("ACCEPTED", fake_out.getvalue())

    @patch('pydot.Dot')
    def test_visualisation(self, mock_dot):
        """Test that visualisation calls Pydot correctly"""
        # We don't want to actually generate files, just check calls
        self.adm.visualiseNetwork(filename="test.png")
        self.assertTrue(mock_dot.called)
        
        # Check basic graph properties were set
        instance = mock_dot.return_value
        instance.write_png.assert_called_with("test.png")
        
    # --- ADD THESE METHODS TO TestADMStructureAndFeatures ---

    @patch('os.makedirs')
    @patch('os.path.exists')
    def test_visualise_sub_adms_integration(self, mock_exists, mock_makedirs):
        """
        Test that Sub-ADM instances stored in facts can be retrieved and visualized.
        Simulates the logic used by UI/Helper methods.
        """
        # 1. Setup Mock Sub-ADM
        mock_sub = MagicMock()
        mock_sub.case = ["SubItem"]
        
        # 2. Simulate Facts storing the instance (as SubADMNode does)
        # Key format: '{NodeName}_sub_adm_instances'
        self.adm.setFact("MySubNode_sub_adm_instances", {"Item 1": mock_sub})
        
        # 3. Retrieve and Visualize (Simulating the UI loop)
        sub_instances = self.adm.getFact("MySubNode_sub_adm_instances")
        
        for item_name, sub_inst in sub_instances.items():
            # Verify we got the object back
            self.assertEqual(sub_inst, mock_sub)
            
            # Call visualize (Mocked)
            sub_inst.visualiseNetwork(filename=f"test_{item_name}.png", case=sub_inst.case)
            
            # 4. Verify Call
            sub_inst.visualiseNetwork.assert_called_with(
                filename="test_Item 1.png", 
                case=["SubItem"]
            )

    @patch('pydot.Dot')
    @patch('pydot.Node')
    @patch('pydot.Edge')
    def test_visualisation_shapes(self, mock_edge, mock_node, mock_dot):
        """
        Test that Special Nodes (SubADM, Evaluation) get distinct shapes.
        """
        # 1. Inject a SubADMNode (Mocking init to bypass complex args)
        with patch('ADM_Construction.SubADMNode.__init__', return_value=None):
            sub_node = SubADMNode("SubProc", None, None)
            sub_node.name = "SubProc"
            sub_node.children = []
            sub_node.acceptance = []
            self.adm.nodes["SubProc"] = sub_node

        # 2. Inject an EvaluationNode
        with patch('ADM_Construction.EvaluationNode.__init__', return_value=None):
            eval_node = EvaluationNode("EvalCheck", None, None)
            eval_node.name = "EvalCheck"
            eval_node.children = []
            eval_node.acceptance = []
            self.adm.nodes["EvalCheck"] = eval_node

        # Run Visualization
        self.adm.visualiseNetwork()
        
        # 3. Verify 'component' shape for SubADMNode
        found_sub_shape = False
        for call in mock_node.call_args_list:
            if call.args[0] == "SubProc" and call.kwargs.get('shape') == "component":
                found_sub_shape = True
                break
        self.assertTrue(found_sub_shape, "SubADMNode should have 'component' shape")

        # 4. Verify 'box' shape + 'peripheries=2' for EvaluationNode
        found_eval_shape = False
        for call in mock_node.call_args_list:
            if call.args[0] == "EvalCheck":
                if call.kwargs.get('shape') == "box" and call.kwargs.get('peripheries') == "2":
                    found_eval_shape = True
                    break
        self.assertTrue(found_eval_shape, "EvaluationNode should have double-box shape")

class TestEvaluationNode(unittest.TestCase):
    """Tests for EvaluationNode logic (Aggregating Sub-ADM results)"""

    def setUp(self):
        self.adm = ADM("EvalTest")

    def test_evaluation_node_normal(self):
        """Test EvaluationNode (Target In Results) - Standard Acceptance"""
        self.adm.addEvaluationNode("Eval1", source_blf="Sub1", target_node="Target", rejection_condition=False)
        node = self.adm.nodes["Eval1"]
        
        # Scenario: Target found in at least one sub-case
        # Case 1: ["Target", "A"] -> Found
        # Case 2: ["B"]          -> Not Found
        self.adm.setFact("Sub1_results", [["Target", "A"], ["B"]])
        
        with patch('sys.stdout', new=io.StringIO()):
            res = node.evaluateResults(self.adm)
        
        self.assertTrue(res)

    def test_evaluation_node_normal_fail(self):
        """Test EvaluationNode (Target In Results) - Standard Rejection"""
        self.adm.addEvaluationNode("Eval1", source_blf="Sub1", target_node="Target", rejection_condition=False)
        node = self.adm.nodes["Eval1"]
        
        # Scenario: Target never appears
        self.adm.setFact("Sub1_results", [["A"], ["B"]])
        
        with patch('sys.stdout', new=io.StringIO()):
            res = node.evaluateResults(self.adm)
        
        self.assertFalse(res)

    def test_evaluation_node_rejection_condition_success(self):
        """Test EvaluationNode with RejectionCondition=True (Success = Target NOT found)"""
        # We want to confirm that "BadThing" is absent from the results
        self.adm.addEvaluationNode("EvalRej", source_blf="Sub1", target_node="BadThing", rejection_condition=True)
        node = self.adm.nodes["EvalRej"]
        
        # Scenario: "BadThing" is NOT in the results -> Success (True)
        self.adm.setFact("Sub1_results", [["GoodThing", "A"], ["B"]])
        
        with patch('sys.stdout', new=io.StringIO()):
            res = node.evaluateResults(self.adm)
            
        self.assertTrue(res)

    def test_evaluation_node_rejection_condition_fail(self):
        """Test EvaluationNode with RejectionCondition=True (Fail = Target FOUND)"""
        self.adm.addEvaluationNode("EvalRej", source_blf="Sub1", target_node="BadThing", rejection_condition=True)
        node = self.adm.nodes["EvalRej"]
        
        # Scenario: "BadThing" IS found -> Failure (False)
        self.adm.setFact("Sub1_results", [["BadThing", "A"], ["B"]])
        
        with patch('sys.stdout', new=io.StringIO()):
            res = node.evaluateResults(self.adm)
            
        self.assertFalse(res)

    def test_evaluation_node_missing_data(self):
        """Test robustness when the source results are missing (NameError handled internally)"""
        self.adm.addEvaluationNode("EvalEmpty", source_blf="NonExistent", target_node="Target")
        node = self.adm.nodes["EvalEmpty"]
        
        # We do NOT set "NonExistent_results"
        # The code catches Exception and returns False
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            res = node.evaluateResults(self.adm)
            
        self.assertFalse(res)
        self.assertIn("Error evaluating", fake_out.getvalue())

class TestSubADMNode(unittest.TestCase):
    """
    Comprehensive tests for SubADMNode.
    Covers: Initialization, Item Retrieval, Aggregation Logic, and Rejection Modes.
    """

    def setUp(self):
        # 1. Create Main ADM
        self.main_adm = ADM("MainADM")
        
        # 2. Simulate Facts in Main ADM
        self.main_adm.setFact("INVENTION_TITLE", "AI System")
        self.main_adm.setFact("TECHNICAL_FIELD", "Computer Science")

        # 3. Create UI Mock
        self.ui_mock = MagicMock()
        self.ui_mock.adm = self.main_adm
        
        # 4. Mock Factory and Function
        self.mock_sub_adm_factory = MagicMock()
        self.mock_item_func = MagicMock(return_value=["ItemA", "ItemB"])

    def test_init_attributes(self):
        """Test correct attribute initialization"""
        node = SubADMNode("SubNode", self.mock_sub_adm_factory, self.mock_item_func, rejection_condition=True, check_node=["A"])
        
        self.assertEqual(node.name, "SubNode")
        self.assertTrue(node.rejection_condition)
        self.assertEqual(node.check_node, ["A"])
        self.assertEqual(node.sub_adm, self.mock_sub_adm_factory)

    def test_fact_propagation(self):
        """Test that ALL facts from Main ADM are copied to the Sub-ADM."""
        node = SubADMNode("FactPropNode", self.mock_sub_adm_factory, ["ItemA"])
        node.main_adm = self.main_adm

        mock_sub_instance = MagicMock()
        mock_sub_instance.case = []
        mock_sub_instance.facts = {} 
        self.mock_sub_adm_factory.return_value = mock_sub_instance

        node._evaluateSubADMWithUI = MagicMock(return_value=(True, [], MagicMock()))

        with patch('sys.stdout', new=io.StringIO()):
            node.evaluateSubADMs(self.ui_mock)

        self.assertEqual(mock_sub_instance.facts["INVENTION_TITLE"], "AI System")
        self.assertEqual(mock_sub_instance.facts, self.main_adm.facts)

    def test_evaluate_standard_mode_success(self):
        """Test Standard Mode: Accept if AT LEAST ONE item is accepted."""
        node = SubADMNode("SubStd", self.mock_sub_adm_factory, ["ItemA", "ItemB"], rejection_condition=False)
        
        # ItemA Passes, ItemB Fails
        node._evaluateSubADMWithUI = MagicMock(side_effect=[
            (True, ["Root"], MagicMock()), 
            (False, [], MagicMock())
        ])

        with patch('sys.stdout', new=io.StringIO()):
            result = node.evaluateSubADMs(self.ui_mock)

        self.assertTrue(result)
        # Check Facts using the correct Node Name prefix
        self.assertEqual(self.main_adm.getFact("SubStd_accepted_count"), 1)
        self.assertEqual(self.main_adm.getFact("SubStd_rejected_count"), 1)

    def test_evaluate_rejection_mode_failure(self):
        """Test Rejection Mode Failure: Reject if ANY item fails."""
        node = SubADMNode("SubRejFail", self.mock_sub_adm_factory, ["ItemA", "ItemB"], rejection_condition=True)
        
        # ItemA Passes, ItemB Fails
        node._evaluateSubADMWithUI = MagicMock(side_effect=[
            (True, ["Root"], MagicMock()), 
            (False, [], MagicMock())
        ])

        with patch('sys.stdout', new=io.StringIO()):
            result = node.evaluateSubADMs(self.ui_mock)

        self.assertFalse(result)
        
        # CORRECTED ASSERTION: Use "SubRejFail" (Node Name) not "SubRej"
        self.assertEqual(self.main_adm.getFact("SubRejFail_rejected_count"), 1)

    def test_evaluate_rejection_mode_success(self):
        """Test Rejection Mode Success: Accept only if ZERO items fail."""
        node = SubADMNode("SubRejPass", self.mock_sub_adm_factory, ["ItemA", "ItemB"], rejection_condition=True)
        
        # Both Pass
        node._evaluateSubADMWithUI = MagicMock(return_value=(True, ["Root"], MagicMock()))

        with patch('sys.stdout', new=io.StringIO()):
            result = node.evaluateSubADMs(self.ui_mock)

        self.assertTrue(result)
        self.assertEqual(self.main_adm.getFact("SubRejPass_rejected_count"), 0)

    def test_get_source_items_dynamic(self):
        """Test retrieving items via function call using Main ADM facts"""
        def get_items_from_facts(adm):
            title = adm.getFact("INVENTION_TITLE")
            return [f"Feature of {title}"]

        node = SubADMNode("DynamicItems", None, get_items_from_facts)
        node.main_adm = self.main_adm
        
        items = node._get_source_items()
        self.assertEqual(items, ["Feature of AI System"])

class TestCoverageGaps(unittest.TestCase):
    """
    Targeted tests to fill coverage gaps in Visualization, Error Handling,
    and complex Logic/Explanation paths.
    """

    def setUp(self):
        self.adm = ADM("GapTest")

    # --- 1. VISUALIZATION COVERAGE (Lines ~682-800) ---
    @patch('pydot.Dot')
    @patch('pydot.Node')
    @patch('pydot.Edge')
    def test_visualisation_branches(self, mock_edge, mock_node, mock_dot):
        """
        Test all logic branches in visualiseNetwork:
        - Colors (In Case vs Out of Case)
        - Shapes (Root vs Issue vs Leaf)
        - Edge Labels ('+' vs '-')
        """
        # Setup ADM with rich structure
        self.adm.addNodes("Leaf")
        self.adm.addNodes("Issue", acceptance=["Leaf"])  # Non-Leaf
        self.adm.addNodes("Root", acceptance=["Issue", "reject Leaf"], root=True) # Root with Reject (Edge Label logic)
        
        # Case state: Issue is IN, Leaf is OUT
        case = ["Issue"]
        
        # Run Visualization
        self.adm.visualiseNetwork(filename="test.png", case=case)
        
        # Verify Edge Logic
        # We expect an edge from Root -> Leaf with label "-" (because of 'reject Leaf')
        # We expect an edge from Root -> Issue with label "+" (default)
        
        # Check that Edge was called with label="-"
        # Asserting calls is tricky with multiple calls, so we check if ANY call matched
        found_negative_edge = False
        for call in mock_edge.call_args_list:
            if call.kwargs.get('label') == "-":
                found_negative_edge = True
                break
        self.assertTrue(found_negative_edge, "Should generate a negative edge for 'reject' condition")

        # Verify Node Shapes/Colors
        # Root should be doubleoctagon
        found_root_shape = False
        for call in mock_node.call_args_list:
            if call.args[0] == "Root" and call.kwargs.get('shape') == "doubleoctagon":
                found_root_shape = True
                break
        self.assertTrue(found_root_shape, "Root should have doubleoctagon shape")

    @patch('pydot.Dot')
    def test_visualisation_minimalist(self, mock_dot):
        """Test visualiseMinimalist execution"""
        self.adm.addNodes("Root", root=True)
        self.adm.visualiseMinimalist("min.png")
        self.assertTrue(mock_dot.return_value.write_png.called)

    @patch('pydot.Dot')
    def test_visualisation_exceptions(self, mock_dot):
        """Test exception handling in visualization (Lines ~751, ~794)"""
        mock_dot.return_value.write_png.side_effect = Exception("Graphviz Missing")
        
        # Should print error but not crash
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            self.adm.visualiseNetwork()
            self.assertIn("Could not generate graph", fake_out.getvalue())
            
            self.adm.visualiseMinimalist()
            self.assertIn("Graphviz Error", fake_out.getvalue())

    # --- 2. EARLY STOP & EXPLANATION GAPS (Lines ~290, ~399) ---

    def test_early_stop_exception(self):
        """Test Exception block in check_early_stop (Line ~308)"""
        # Force an error by corrupting state
        self.adm.root_node = "NotANodeObject" # This will cause evaluateNode to crash
        
        with self.assertRaises(ValueError):
            self.adm.check_early_stop([])

    def test_early_stop_definitive_reject_but_unknown_positive(self):
        """If root acceptance is [B, reject C], C true but B unknown -> no early stop."""
        # Setup nodes B and C and root A with acceptance [B, reject C]
        self.adm.addNodes("B")
        self.adm.addNodes("C")
        self.adm.addNodes("A", acceptance=["B", "reject C"], root=True)
        self.adm.root_node = self.adm.nodes["A"]

        # Case: C present (so 'reject C' condition is True), B not evaluated (Unknown)
        self.adm.case = ["C"]
        evaluated_nodes = {"C"}

        # Early stop should NOT trigger because there is an unknown positive (B)
        result = self.adm.check_early_stop(evaluated_nodes)
        self.assertFalse(result)

    def test_evaluation_node_exception(self):
        """Test EvaluationNode Exception handling (Line ~1422)"""
        # Force error by making getFact raise an unexpected error (not NameError)
        self.adm.getFact = MagicMock(side_effect=Exception("Database Down"))
        
        node = EvaluationNode("EvalCrash", "Source", "Target")
        
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            res = node.evaluateResults(self.adm)
            self.assertFalse(res)
            self.assertIn("Error evaluating EvalCrash", fake_out.getvalue())

    def test_sub_adm_init_validation(self):
        """Test SubADMNode check_node validation (Line ~989)"""
        with self.assertRaises(ValueError):
            # check_node must be a list
            SubADMNode("BadInit", None, [], check_node="NotAList")

class TestSubADM1(unittest.TestCase):
    """
    Tests for Sub-ADM 1 (Reliable Technical Effect Analysis).
    Verifies logic for Technical Contribution, Exclusions, and Credibility.
    """

    def setUp(self):
        # Initialize Sub-ADM 1 for a dummy feature
        self.sub_adm = sub_adm_1("TestFeature")
        self.sub_adm.case = ["DistinguishingFeatures"] # Base assumption for sub-adm run

    def evaluate_case(self, case_items):
        """Helper to run evaluation for a specific set of inputs with stdout suppression."""
        # Reset case to base
        self.sub_adm.case = ["DistinguishingFeatures"]
        # Add test inputs
        self.sub_adm.case.extend(case_items)
        
        # Run tree evaluation with suppression
        with redirect_stdout(io.StringIO()):
            result = self.sub_adm.evaluateTree(self.sub_adm.case)
            
        return result

    def test_independent_technical_contribution(self):
        """
        Scenario: Feature makes an independent technical contribution.
        Expected: FeatureTechnicalContribution -> FeatureReliableTechnicalEffect (if credible)
        """
        inputs = ["IndependentContribution", "Credible", "Reproducible"]
        
        # Run evaluation
        self.evaluate_case(inputs)
        
        # Assertions
        self.assertIn("IndependentContribution", self.sub_adm.case)
        self.assertIn("NormalTechnicalContribution", self.sub_adm.case)
        self.assertIn("FeatureTechnicalContribution", self.sub_adm.case)
        self.assertIn("FeatureReliableTechnicalEffect", self.sub_adm.case)
        
        # Verify no exclusions triggered
        self.assertNotIn("ExcludedField", self.sub_adm.case)

    def test_excluded_field_simulation(self):
        """
        Scenario: Computer Simulation WITHOUT Technical Adaptation.
        Expected: Rejection (ExcludedField -> reject NormalTechnicalContribution)
        """
        inputs = ["ComputerSimulation", "Credible", "Reproducible"]
        # Note: Missing "TechnicalAdaptation" or "IntendedTechnicalUse"
        
        self.evaluate_case(inputs)
        
        self.assertIn("ExcludedField", self.sub_adm.case) # ComputerSimulation triggers this
        self.assertIn("NumOrComp", self.sub_adm.case)
        
        # Should be rejected
        self.assertNotIn("NormalTechnicalContribution", self.sub_adm.case)
        self.assertNotIn("FeatureReliableTechnicalEffect", self.sub_adm.case)

    def test_valid_simulation_contribution(self):
        """
        Scenario: Computer Simulation WITH Technical Adaptation.
        Expected: Acceptance (ComputationalContribution -> FeatureTechnicalContribution)
        """
        inputs = ["ComputerSimulation", "TechnicalAdaptation", "Credible", "Reproducible"]
        
        self.evaluate_case(inputs)
        
        self.assertIn("ComputationalContribution", self.sub_adm.case)
        self.assertIn("FeatureTechnicalContribution", self.sub_adm.case)
        self.assertIn("FeatureReliableTechnicalEffect", self.sub_adm.case)

    def test_mathematical_method_exclusion(self):
        """
        Scenario: Pure Mathematical Method (No Specific Purpose).
        Expected: Rejection
        """
        inputs = ["MathematicalMethod", "Credible"]
        
        self.evaluate_case(inputs)
        
        # "MathematicalMethod" -> ExcludedField
        self.assertIn("ExcludedField", self.sub_adm.case)
        self.assertNotIn("MathematicalContribution", self.sub_adm.case)
        self.assertNotIn("FeatureTechnicalContribution", self.sub_adm.case)

    def test_mathematical_method_valid(self):
        """
        Scenario: Mathematical Method applied in field (Specific Purpose + Functionally Limited).
        Expected: Acceptance
        """
        inputs = ["MathematicalMethod", "SpecificPurpose", "FunctionallyLimited", "Credible", "Reproducible"]
        
        self.evaluate_case(inputs)
        
        self.assertIn("AppliedInField", self.sub_adm.case)
        self.assertIn("MathematicalContribution", self.sub_adm.case)
        self.assertIn("FeatureReliableTechnicalEffect", self.sub_adm.case)

    def test_non_reproducible_rejection(self):
        """
        Scenario: Valid Technical Contribution but NOT Reproducible.
        Expected: Rejection of ReliableTechnicalEffect
        """
        inputs = ["IndependentContribution", "Credible", "NonReproducible"]
        
        self.evaluate_case(inputs)
        
        # Logic check:
        # FeatureTechnicalContribution is True (it is technical)
        self.assertIn("FeatureTechnicalContribution", self.sub_adm.case)
        
        # BUT FeatureReliableTechnicalEffect has "reject NonReproducible"
        self.assertIn("NonReproducible", self.sub_adm.case)
        self.assertNotIn("FeatureReliableTechnicalEffect", self.sub_adm.case)

    def test_bonus_effect_rejection(self):
        """
        Scenario: Valid Contribution but it's just a 'Bonus Effect' (One Way Street).
        Expected: Rejection of ReliableTechnicalEffect
        """
        inputs = ["IndependentContribution", "Credible", "Reproducible", 
                  "UnexpectedEffect", "OneWayStreet"]
        
        self.evaluate_case(inputs)
        
        self.assertIn("BonusEffect", self.sub_adm.case)
        self.assertNotIn("FeatureReliableTechnicalEffect", self.sub_adm.case)

class TestSubADM2(unittest.TestCase):
    """
    Tests for Sub-ADM 2 (Objective Technical Problem & Obviousness).
    Verifies logic for Problem Formulation, Hindsight, and 'Would Have Arrived'.
    """

    def setUp(self):
        self.sub_adm = sub_adm_2("TestOTP")
        # Base case usually starts empty or with basic setup
        self.sub_adm.case = []

    def evaluate_case(self, case_items):
        """Helper to evaluate with stdout suppression."""
        self.sub_adm.case = []
        self.sub_adm.case.extend(case_items)
        
        with redirect_stdout(io.StringIO()):
            self.sub_adm.evaluateTree(self.sub_adm.case)
        
        return self.sub_adm.case

    def test_hindsight_rejection(self):
        """
        Scenario: Formulated with Hindsight.
        Expected: WellFormed -> Rejected
        """
        inputs = ["Encompassed", "Embodied", "ScopeOfClaim", 
                  "WrittenFormulation", "Hindsight"]
        
        self.evaluate_case(inputs)
        
        # BasicFormulation is OK
        self.assertIn("BasicFormulation", self.sub_adm.case)
        
        # But 'WellFormed' rejects 'Hindsight'
        self.assertIn("Hindsight", self.sub_adm.case)
        self.assertNotIn("WellFormed", self.sub_adm.case)
        self.assertNotIn("ObjectiveTechnicalProblemFormulation", self.sub_adm.case)

    def test_valid_otp_unconstrained(self):
        """
        Scenario: Valid OTP, no non-technical constraints.
        Expected: ObjectiveTechnicalProblemFormulation -> Accepted
        """
        inputs = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation"]
        
        self.evaluate_case(inputs)
        
        self.assertIn("BasicFormulation", self.sub_adm.case)
        self.assertIn("WellFormed", self.sub_adm.case)
        
        # ConstrainedProblem check: Needs 'WellFormed' AND 'NonTechnicalContribution'.
        # Here 'NonTechnicalContribution' is missing, so ConstrainedProblem is False.
        self.assertNotIn("ConstrainedProblem", self.sub_adm.case)
        
        # ObjectiveTechnicalProblemFormulation accepts 'WellFormed' (Or 'ConstrainedProblem')
        # Wait, let's check the logic in inventive_step_ADM.py for 'ObjectiveTechnicalProblemFormulation':
        # "ObjectiveTechnicalProblemFormulation", ['ConstrainedProblem','WellFormed']
        # This is an OR condition (implied by separate strings in list). 
        # So if WellFormed is True, OTPFormulation is True.
        self.assertIn("ObjectiveTechnicalProblemFormulation", self.sub_adm.case)

    def test_valid_otp_constrained(self):
        """
        Scenario: Valid OTP, constrained by non-technical contribution.
        Expected: ConstrainedProblem -> True, OTPFormulation -> True
        """
        inputs = ["Encompassed", "Embodied", "ScopeOfClaim", 
                  "WrittenFormulation", "NonTechnicalContribution"]
        
        self.evaluate_case(inputs)
        
        self.assertIn("WellFormed", self.sub_adm.case)
        self.assertIn("ConstrainedProblem", self.sub_adm.case)
        self.assertIn("ObjectiveTechnicalProblemFormulation", self.sub_adm.case)

    def test_would_have_arrived_modification(self):
        """
        Scenario: Skilled person 'WouldModify' the prior art.
        Expected: WouldHaveArrived -> True (Obvious)
        """
        inputs = ["Encompassed", "Embodied", "ScopeOfClaim", 
                  "WrittenFormulation", "WouldModify"]
        
        self.evaluate_case(inputs)
        
        self.assertIn("ObjectiveTechnicalProblemFormulation", self.sub_adm.case)
        self.assertIn("WouldHaveArrived", self.sub_adm.case)

    def test_would_have_arrived_adaptation(self):
        """
        Scenario: Skilled person 'WouldAdapt' the prior art.
        Expected: WouldHaveArrived -> True (Obvious)
        """
        inputs = ["Encompassed", "Embodied", "ScopeOfClaim", 
                  "WrittenFormulation", "WouldAdapt"]
        
        self.evaluate_case(inputs)
        
        self.assertIn("ObjectiveTechnicalProblemFormulation", self.sub_adm.case)
        self.assertIn("WouldHaveArrived", self.sub_adm.case)

    def test_not_obvious_conclusion(self):
        """
        Scenario: Valid OTP, but skilled person would NOT modify/adapt (Neither selected).
        Expected: WouldHaveArrived -> False (Not Obvious)
        """
        inputs = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation"]
        # Note: 'WouldModify' and 'WouldAdapt' are absent
        
        self.evaluate_case(inputs)
        
        self.assertIn("ObjectiveTechnicalProblemFormulation", self.sub_adm.case)
        
        # Logic: WouldHaveArrived requires (WouldModify AND OTP) OR (WouldAdapt AND OTP)
        self.assertNotIn("WouldHaveArrived", self.sub_adm.case)
        
class TestMainADM(unittest.TestCase):
    """
    Tests for Main Inventive Step ADM.
    Covers: Novelty, EvaluationNodes (linking to Sub-ADM), Objective Technical Problem, and Obviousness.
    """

    def setUp(self):
        self.adm = adm_main()
        self.adm.case = []

    def evaluate_case(self, case_items, facts=None):
        """Helper to evaluate main ADM case with stdout suppression."""
        self.adm.case = []
        if facts:
            for k, v in facts.items():
                self.adm.setFact(k, v)
        self.adm.case.extend(case_items)
        
        with redirect_stdout(io.StringIO()):
            result = self.adm.evaluateTree(self.adm.case)
            
        return result

    def test_novelty_check(self):
        """
        Scenario: Distinguishing Features exist.
        Expected: Novelty = True
        """
        # DistinguishingFeatures is an EvaluationNode. 
        # We simulate it being accepted by mocking results fact.
        facts = {
            "ReliableTechnicalEffect_results": [["DistinguishingFeatures"]] 
        }
        
        self.evaluate_case([], facts)
        
        self.assertIn("DistinguishingFeatures", self.adm.case)
        self.assertIn("Novelty", self.adm.case)

    def test_no_technical_contribution(self):
        """
        Scenario: Distinguishing features exist, but Sub-ADM found NO technical contribution.
        Expected:
            - DistinguishingFeatures: True
            - NonTechnicalContribution: True (Rejection Condition triggered: 'FeatureTechnicalContribution' missing)
            - TechnicalContribution: False
            - InvStep: False (Rejected due to 'Obvious' or Lack of Tech Contribution path)
        """
        # Sub-ADM Result: Just the feature name, NO "FeatureTechnicalContribution" tag
        facts = {
            "ReliableTechnicalEffect_results": [["DistinguishingFeatures", "Credible"]] 
        }
        
        self.evaluate_case([], facts)
        
        self.assertIn("DistinguishingFeatures", self.adm.case)
        
        # NonTechnicalContribution (EvalNode): reject_condition=True.
        # Target "FeatureTechnicalContribution" is MISSING from results.
        # So NonTechnicalContribution -> Accepted (True).
        self.assertIn("NonTechnicalContribution", self.adm.case)
        
        # TechnicalContribution (EvalNode): reject_condition=False.
        # Target "FeatureTechnicalContribution" is MISSING.
        # So TechnicalContribution -> Rejected (False).
        self.assertNotIn("TechnicalContribution", self.adm.case)
        
        # Contribution Node logic: 'TechnicalContribution' is False.
        self.assertNotIn("Contribution", self.adm.case) # Requires TechnicalContribution

    def test_inventive_step_success(self):
        """
        Scenario:
            - Technical Contribution Exists
            - Valid Objective Technical Problem (OTP)
            - Not Obvious
        Expected: InvStep = True
        """
        # 1. Setup Facts for Sub-ADM Results
        facts = {
            "ReliableTechnicalEffect_results": [["DistinguishingFeatures", "FeatureTechnicalContribution"]],
            
            # OTPObvious results: Root "WouldHaveArrived" NOT present -> Not Obvious
            # OTPObvious is a RejectionCondition=True node.
            # If rejected_count > 0, the node evaluates to FALSE (Accepted as Not Obvious)
            # Wait, RejectionCondition=True means: 
            #   - If Target Found in ANY item -> Return False (Node Rejected)
            #   - If Target NOT Found -> Return True (Node Accepted)
            
            # Here Target is "WouldHaveArrived". We want "Not Obvious", so we want "WouldHaveArrived" to be MISSING.
            # So the result list should NOT contain "WouldHaveArrived".
            "OTPNotObvious_results": [["ObjectiveTechnicalProblemFormulation"]], 
            "OTPNotObvious_rejected_count": 0, # Logic check variable, usually handled by node evaluation
            "OTPNotObvious_accepted_count": 1
        }
        
        # 2. Run Evaluation
        # FIX: We MUST add 'ReliableTechnicalEffect' to the case manually.
        # In a real run, the SubADMNode adds itself to the case upon success.
        # Without it, neither 'Combination' nor 'PartialProblems' can trigger.
        
        self.evaluate_case(["Novelty", "TechnicalContribution", "ReliableTechnicalEffect","OTPNotObvious"], facts)
        
        # 3. Verify Components
        self.assertIn("TechnicalContribution", self.adm.case)
        
        # Verify PartialProblems logic triggered (Standard aggregation)
        # Combination fails (no Synergy), so PartialProblems = True
        self.assertIn("PartialProblems", self.adm.case) 
        
        self.assertIn("Contribution", self.adm.case)
        self.assertIn("CandidateOTP", self.adm.case)
        self.assertIn("ValidOTP", self.adm.case)
        self.assertIn("ObjectiveTechnicalProblem", self.adm.case)
        
        # Verify Obviousness is rejected
        self.assertNotIn("Obvious", self.adm.case)
        
        # FINAL ASSERTION
        self.assertIn("InvStep", self.adm.case)

    def test_secondary_indicator_obviousness(self):
        """
        Scenario: Not Obvious via OTP, but Secondary Indicator (e.g. Aggregation/KnownMeasures) present.
        Expected: InvStep = False
        """
        facts = {
            "ReliableTechnicalEffect_results": [["FeatureTechnicalContribution"]],
            # OTP Not Obvious
            "OTPNotObvious_results": [["ObjectiveTechnicalProblemFormulation"]], 
            "OTPNotObvious_rejected_count": 1
        }
        
        # Add "KnownMeasures" to case (Secondary Indicator)
        # "GapFilled" -> "KnownMeasures"
        self.evaluate_case(["GapFilled"], facts)
        
        self.assertNotIn("OTPNotObvious", self.adm.case)
        self.assertIn("KnownMeasures", self.adm.case)
        self.assertIn("SecondaryIndicator", self.adm.case)
        
        # Obvious = OTPObvious OR SecondaryIndicator
        self.assertIn("Obvious", self.adm.case)
        
        self.assertNotIn("InvStep", self.adm.case)

import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import io
import os
import builtins

# Import the CLI class and relevant ADM construction classes
from UI import CLI
from ADM_Construction import Node, SubADMNode, EvaluationNode

class TestUI(unittest.TestCase):
    """
    Test Suite for UI.py (CLI Class)
    Covers: Initialization, Question Generation, Gate Logic, and Workflows.
    """

    def setUp(self):
        """Set up a fresh CLI instance and Mock ADM for each test"""
        self.mock_adm = MagicMock()
        # Basic ADM Attributes
        self.mock_adm.nodes = {}
        self.mock_adm.questionOrder = []
        self.mock_adm.information_questions = {}
        self.mock_adm.question_instantiators = {}
        self.mock_adm.case = []
        self.mock_adm.root_node = MagicMock()
        self.mock_adm.root_node.name = "Root"
        self.mock_adm.facts = {}
        
        # Default Method Mocks
        self.mock_adm.check_early_stop.return_value = False
        self.mock_adm.resolveQuestionTemplate.side_effect = lambda x: x # Identity function
        self.mock_adm.evaluateTree.return_value = []
        
        self.cli = CLI(self.mock_adm)

    # --- 1. INITIALIZATION & QUERY DOMAIN ---
    
    @patch('builtins.input', side_effect=["MyTestCase"])
    def test_query_domain_sets_casename(self, mock_input):
        """Test that query_domain asks for a case name if missing"""
        # Mock ask_questions so it doesn't actually run the loop
        self.cli.ask_questions = MagicMock()
        
        self.cli.query_domain()
        
        self.assertEqual(self.cli.caseName, "MyTestCase")
        self.cli.ask_questions.assert_called_once()

    # --- 2. QUESTION GENERATION LOGIC ---

    def test_questiongen_empty(self):
        """Test questiongen returns empty when no questions remain"""
        order, nodes = self.cli.questiongen([], {})
        self.assertEqual(order, [])

    def test_early_stop_trigger(self):
        """Test that questiongen halts if ADM.check_early_stop returns True"""
        self.cli.evaluated_blfs = {"SomeNode"}
        self.mock_adm.check_early_stop.return_value = True
        
        order, nodes = self.cli.questiongen(["NextQ"], {})
        
        # Should return empty list (stop recursion)
        self.assertEqual(order, [])
        self.mock_adm.check_early_stop.assert_called()

    @patch('builtins.input', side_effect=["InfoAnswer"])
    def test_info_question_handling(self, mock_input):
        """Test handling of Information Questions"""
        # Setup
        q_name = "INFO_Q"
        self.mock_adm.information_questions = {q_name: "What is X?"}
        
        # Run
        order, nodes = self.cli.questiongen([q_name], {})
        
        # Assertions
        self.mock_adm.setFact.assert_called_with(q_name, "InfoAnswer")
        self.assertEqual(order, []) # Should pop the question

    # --- 3. QUESTION HELPER & INSTANTIATORS ---

    @patch('builtins.input', side_effect=["1"]) # Select option 1
    @patch('builtins.print')
    def test_question_instantiator_selection(self, mock_print, mock_input):
        """Test picking an answer from a Question Instantiator"""
        q_name = "PickType"
        instantiator = {
            'question': "Type?",
            'blf_mapping': {
                "Option A": "TypeA",
                "Option B": "TypeB"
            },
            'gating_node': None
        }
        self.mock_adm.question_instantiators = {q_name: instantiator}
        
        # Run helper directly
        self.cli.questionHelper(None, q_name)
        
        # Assertions
        self.assertIn("TypeA", self.cli.case)
        self.assertNotIn("TypeB", self.cli.case)

    @patch('builtins.input', side_effect=["1", "FactAnswer"]) # Option 1 -> Fact Question
    @patch('builtins.print')
    def test_question_instantiator_factual_ascription(self, mock_print, mock_input):
        """Test Factual Ascription triggered by an Instantiator choice"""
        q_name = "PickFact"
        instantiator = {
            'question': "Select?",
            'blf_mapping': {"Option A": "TypeA"},
            'factual_ascription': {
                "TypeA": {"FactKey": "Describe A"}
            }
        }
        self.mock_adm.question_instantiators = {q_name: instantiator}
        
        self.cli.questionHelper(None, q_name)
        
        self.assertIn("TypeA", self.cli.case)
        self.mock_adm.setFact.assert_called_with("FactKey", "FactAnswer")

    # --- 4. STANDARD NODE HANDLING ---

    @patch('builtins.input', side_effect=["y"])
    def test_regular_node_yes(self, mock_input):
        """Test answering 'yes' adds node to case"""
        node = MagicMock()
        node.question = "Is it A?"
        
        self.cli.questionHelper(node, "NodeA")
        
        self.assertIn("NodeA", self.cli.case)

    @patch('builtins.input', side_effect=["n"])
    def test_regular_node_no(self, mock_input):
        """Test answering 'no' does NOT add node to case"""
        node = MagicMock()
        node.question = "Is it A?"
        
        self.cli.questionHelper(node, "NodeA")
        
        self.assertNotIn("NodeA", self.cli.case)

    # --- 5. GATE LOGIC ---

    def test_gates_satisfied_no_dependencies(self):
        """Test gates_satisfied returns True for node with no gates"""
        node = MagicMock()
        del node.check_gated # Ensure it doesn't look like a GatedBLF
        del node.gated_node
        
        self.assertTrue(self.cli.gates_satisfied(node, []))

    def test_gates_satisfied_gated_blf(self):
        """Test gates_satisfied delegates to check_gated if present"""
        node = MagicMock()
        node.check_gated.return_value = True
        
        self.assertTrue(self.cli.gates_satisfied(node, []))
        node.check_gated.assert_called()

    def test_evaluate_gates_success(self):
        """Test evaluateGates successfully evaluates a parent node"""
        # Setup: GateNode has logic that passes
        gate_node = MagicMock()
        gate_node.acceptance = ["A"]
        gate_node.children = []
        
        self.mock_adm.nodes = {"GateNode": gate_node}
        
        # Mock evaluateNode to return True
        self.mock_adm.evaluateNode.return_value = (True, 0)
        
        res = self.cli.evaluateGates("GateNode", "CurrentQ")
        
        self.assertTrue(res)
        self.assertIn("GateNode", self.cli.case)

    def test_evaluate_gates_failure(self):
        """Test evaluateGates returns False if parent logic fails"""
        gate_node = MagicMock()
        gate_node.acceptance = ["A"]
        
        self.mock_adm.nodes = {"GateNode": gate_node}
        self.mock_adm.evaluateNode.return_value = (False, -1)
        
        res = self.cli.evaluateGates("GateNode", "CurrentQ")
        
        self.assertFalse(res)
        self.assertNotIn("GateNode", self.cli.case)

    # --- 6. SPECIAL NODES (SubADM / Evaluation) ---

    def test_questiongen_subadm_node(self):
        """Test handling of SubADMNode execution"""
        sub_node = SubADMNode("SubProc", None, None)
        # Mock evaluateSubADMs to return True
        sub_node.evaluateSubADMs = MagicMock(return_value=True)
        
        self.mock_adm.nodes = {"SubProc": sub_node}
        
        order, _ = self.cli.questiongen(["SubProc"], self.mock_adm.nodes)
        
        self.assertIn("SubProc", self.cli.case)
        self.assertIn("SubProc", self.cli.evaluated_blfs)
        sub_node.evaluateSubADMs.assert_called_with(ui_instance=self.cli)

    def test_questiongen_evaluation_node(self):
        """Test handling of EvaluationNode execution"""
        eval_node = EvaluationNode("EvalCheck", "Source", "Target")
        # Mock evaluateResults to return True
        eval_node.evaluateResults = MagicMock(return_value=True)
        
        self.mock_adm.nodes = {"EvalCheck": eval_node}
        
        order, _ = self.cli.questiongen(["EvalCheck"], self.mock_adm.nodes)
        
        self.assertIn("EvalCheck", self.cli.case)
        eval_node.evaluateResults.assert_called_with(self.mock_adm)

    # --- 7. VISUALIZATION ---

    @patch('os.makedirs')
    @patch('os.path.exists')
    def test_visualize_domain_logic(self, mock_exists, mock_makedirs):
        """Test visualization triggers correct ADM methods and Sub-ADM scanning"""
        self.cli.caseName = "TestVis"
        self.mock_adm.case = ["A"]
        
        # Mock facts containing a Sub-ADM instance
        mock_sub_adm = MagicMock()
        self.mock_adm.facts = {
            "SubNode_sub_adm_instances": {"Item1": mock_sub_adm}
        }
        
        # Mock directory exists check to False so it tries to create dir
        mock_exists.return_value = False
        
        self.cli.visualize_domain(minimal=False)
        
        # Verify Main ADM Viz
        self.mock_adm.visualiseNetwork.assert_called_with(filename="TestVis.png", case=["A"])
        
        # Verify Sub-ADM Viz logic
        mock_makedirs.assert_called_with("TestVis_sub_adms")
        mock_sub_adm.visualiseNetwork.assert_called()
     
if __name__ == '__main__':
    unittest.main()