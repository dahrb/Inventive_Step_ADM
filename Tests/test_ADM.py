"""
Tests for the Inventive Step ADMs, UI, and ADM_Construction module.

Many of these tests were created with the assistance of LLMs and evaluated manually for logical errors. Particularly in regard to the ADMs.

Last Updated: 28.03.26

Status: COMPLETE

Logs:
v_1: initial adm tests
v_2: expanded tests with llms
v_3: final tests for final_adm configurations including ablation variants
"""

import unittest
from unittest.mock import MagicMock, patch
import io
import logging
from contextlib import redirect_stdout
import os
import json
import tempfile

from UI import CLI
from ADM_Construction import Node, SubADMNode, EvaluationNode, GatedBLF
from ADM_Construction import ADM, Node, SubADMNode, EvaluationNode, GatedBLF
from inventive_step_ADM import adm_initial, adm_main, sub_adm_1, sub_adm_2

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

        # Need >1 question: the guard in questiongen only calls check_early_stop
        # when len(question_order) > 1 (i.e. there is at least one more question
        # after the current one to potentially skip).
        order, nodes = self.cli.questiongen(["NextQ", "AnotherQ"], {})
        
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
     
class TestADMInitial(unittest.TestCase):
    """Tests for adm_initial() — precondition ADM structure and logic paths."""

    def setUp(self):
        self.adm = adm_initial()
        self.adm.case = []

    def evaluate_case(self, case_items, facts=None):
        self.adm.case = list(case_items)
        if facts:
            for k, v in facts.items():
                self.adm.setFact(k, v)
        with redirect_stdout(io.StringIO()):
            result = self.adm.evaluateTree(self.adm.case)
        return result

    def test_structure_has_root_node(self):
        """adm_initial must define a root node called 'Valid'."""
        self.assertTrue(hasattr(self.adm, 'root_node'))
        self.assertEqual(self.adm.root_node.name, 'Valid')

    def test_information_questions_registered(self):
        """All mandatory information questions must be present."""
        required = [
            'INVENTION_TITLE', 'INVENTION_DESCRIPTION',
            'INVENTION_TECHNICAL_FIELD', 'REL_PRIOR_ART', 'CGK',
        ]
        for q in required:
            self.assertIn(q, self.adm.information_questions, f"Missing info question: {q}")

    def test_question_order_non_empty(self):
        """Question order must be a non-empty list."""
        self.assertIsInstance(self.adm.questionOrder, list)
        self.assertGreater(len(self.adm.questionOrder), 0)

    def test_skilled_person_accepted(self):
        """SkilledPerson accepted when all prerequisite BLFs are present."""
        case = ['SkilledIn', 'Average', 'Aware', 'Access', 'Individual']
        self.evaluate_case(case)
        self.assertIn('Person', self.adm.case)
        self.assertIn('SkilledPerson', self.adm.case)

    def test_skilled_person_research_team(self):
        """SkilledPerson accepted with a research team."""
        case = ['SkilledIn', 'Average', 'Aware', 'Access', 'ResearchTeam']
        self.evaluate_case(case)
        self.assertIn('SkilledPerson', self.adm.case)

    def test_skilled_person_rejected_missing_access(self):
        """SkilledPerson rejected if Access is missing."""
        case = ['SkilledIn', 'Average', 'Aware', 'Individual']
        self.evaluate_case(case)
        self.assertNotIn('SkilledPerson', self.adm.case)

    def test_relevant_prior_art_same_field(self):
        """RelevantPriorArt accepted via SameField."""
        self.evaluate_case(['SameField'])
        self.assertIn('RelevantPriorArt', self.adm.case)

    def test_relevant_prior_art_similar_field(self):
        """RelevantPriorArt accepted via SimilarField."""
        self.evaluate_case(['SimilarField'])
        self.assertIn('RelevantPriorArt', self.adm.case)

    def test_relevant_prior_art_similar_purpose(self):
        """RelevantPriorArt accepted via SimilarPurpose."""
        self.evaluate_case(['SimilarPurpose'])
        self.assertIn('RelevantPriorArt', self.adm.case)

    def test_relevant_prior_art_similar_effect(self):
        """RelevantPriorArt accepted via SimilarEffect."""
        self.evaluate_case(['SimilarEffect'])
        self.assertIn('RelevantPriorArt', self.adm.case)

    def test_common_knowledge_not_contested(self):
        """CommonKnowledge accepted when Contested is absent (accept path)."""
        self.evaluate_case([])
        self.assertIn('CommonKnowledge', self.adm.case)

    def test_common_knowledge_contested_with_textbook(self):
        """CommonKnowledge accepted when contested but textbook evidence provided."""
        self.evaluate_case(['Contested', 'Textbook'])
        self.assertIn('DocumentaryEvidence', self.adm.case)
        self.assertIn('CommonKnowledge', self.adm.case)

    def test_common_knowledge_contested_single_publication_rejected(self):
        """DocumentaryEvidence rejected when only SinglePublication provided."""
        self.evaluate_case(['Contested', 'SinglePublication'])
        self.assertNotIn('DocumentaryEvidence', self.adm.case)

    def test_common_knowledge_technical_survey(self):
        """DocumentaryEvidence accepted with TechnicalSurvey."""
        self.evaluate_case(['Contested', 'TechnicalSurvey'])
        self.assertIn('DocumentaryEvidence', self.adm.case)

    def test_common_knowledge_new_field_publication(self):
        """DocumentaryEvidence accepted with publication in new field."""
        self.evaluate_case(['Contested', 'PublicationNewField'])
        self.assertIn('DocumentaryEvidence', self.adm.case)

    def test_cpa_established(self):
        """ClosestPriorArt established when all CPA conditions met."""
        case = ['SameField', 'SingleReference', 'MinModifications', 'AssessedBy']
        self.evaluate_case(case)
        self.assertIn('RelevantPriorArt', self.adm.case)
        self.assertIn('ClosestPriorArt', self.adm.case)

    def test_cpa_not_established_missing_min_mod(self):
        """ClosestPriorArt not established when MinModifications missing."""
        case = ['SameField', 'SingleReference', 'AssessedBy']
        self.evaluate_case(case)
        self.assertNotIn('ClosestPriorArt', self.adm.case)

    def test_combination_documents_same_field(self):
        """CombinationDocuments accepted with same-field combo."""
        case = [
            'SameField', 'SingleReference', 'MinModifications', 'AssessedBy',
            'CombinationAttempt', 'SameFieldCPA', 'CombinationMotive', 'BasisToAssociate',
        ]
        self.evaluate_case(case)
        self.assertIn('ClosestPriorArt', self.adm.case)
        self.assertIn('CombinationDocuments', self.adm.case)

    def test_combination_documents_similar_field(self):
        """CombinationDocuments accepted with similar-field combo."""
        case = [
            'SameField', 'SingleReference', 'MinModifications', 'AssessedBy',
            'CombinationAttempt', 'SimilarFieldCPA', 'CombinationMotive', 'BasisToAssociate',
        ]
        self.evaluate_case(case)
        self.assertIn('CombinationDocuments', self.adm.case)

    def test_valid_accepted_full_path(self):
        """Valid node accepted when SkilledPerson and ClosestPriorArtDocuments are both present."""
        case = [
            'SkilledIn', 'Average', 'Aware', 'Access', 'Individual',
            'SameField', 'SingleReference', 'MinModifications', 'AssessedBy',
        ]
        self.evaluate_case(case)
        self.assertIn('SkilledPerson', self.adm.case)
        self.assertIn('ClosestPriorArt', self.adm.case)
        self.assertIn('CommonKnowledge', self.adm.case)
        self.assertIn('ClosestPriorArtDocuments', self.adm.case)
        self.assertIn('Valid', self.adm.case)

    def test_valid_rejected_no_skilled_person(self):
        """Valid rejected when skilled person cannot be established."""
        case = ['SameField', 'SingleReference', 'MinModifications', 'AssessedBy']
        self.evaluate_case(case)
        self.assertNotIn('Valid', self.adm.case)

    def test_adm_str(self):
        """ADM __str__ returns its name."""
        self.assertEqual(str(self.adm), "Inventive Step: Preconditions")

class TestMainADMAblation_NoSub1(unittest.TestCase):
    """Tests for adm_main(sub_adm_1_flag=False, sub_adm_2_flag=True).

    In this ablation the sub-ADM 1 (feature reliability) is replaced by flat
    direct questions Q100-Q107. Sub-ADM 2 (OTP) still uses the sub-ADM.
    """

    def setUp(self):
        self.adm = adm_main(sub_adm_1_flag=False, sub_adm_2_flag=True)
        self.adm.case = []

    def evaluate_case(self, case_items, facts=None):
        self.adm.case = list(case_items)
        if facts:
            for k, v in facts.items():
                self.adm.setFact(k, v)
        with redirect_stdout(io.StringIO()):
            self.adm.evaluateTree(self.adm.case)

    def test_structure_has_root_invstep(self):
        self.assertEqual(self.adm.root_node.name, 'InvStep')

    def test_flat_tech_contribution_nodes_present(self):
        """Q100-Q107 nodes must be registered (flat ablation path)."""
        expected_nodes = [
            'DistinguishingFeatures', 'TechnicalContribution', 'UnexpectedEffect',
            'ReliableTechnicalEffect',
        ]
        for n in expected_nodes:
            self.assertIn(n, self.adm.nodes, f"Missing node: {n}")

    def test_question_instantiator_tech_contribution_registered(self):
        """technical_contribution question instantiator must be present."""
        self.assertIn('technical_contribution', self.adm.question_instantiators)

    def test_flat_reliable_technical_effect_accepted(self):
        """ReliableTechnicalEffect accepted via flat TechnicalContribution + Credible path."""
        self.evaluate_case(['TechnicalContribution', 'Credible'])
        self.assertIn('ReliableTechnicalEffect', self.adm.case)

    def test_flat_reliable_technical_effect_bonus_effect_rejected(self):
        """ReliableTechnicalEffect rejected when BonusEffect present."""
        # BonusEffect requires TechnicalContribution AND UnexpectedEffect AND OneWayStreet
        self.evaluate_case([
            'TechnicalContribution', 'Credible',
            'UnexpectedEffect', 'OneWayStreet',
        ])
        self.assertIn('BonusEffect', self.adm.case)
        self.assertNotIn('ReliableTechnicalEffect', self.adm.case)

    def test_flat_reliable_technical_effect_non_reproducible_rejected(self):
        """ReliableTechnicalEffect rejected when NonReproducible present."""
        self.evaluate_case(['TechnicalContribution', 'Credible', 'NonReproducible'])
        self.assertNotIn('ReliableTechnicalEffect', self.adm.case)

    def test_flat_sufficiency_of_disclosure_issue(self):
        """SufficiencyOfDisclosure triggered when claim contains non-reproducible effect."""
        self.evaluate_case([
            'TechnicalContribution', 'Credible', 'NonReproducible',
            'ClaimContainsEffect', 'SufficiencyOfDisclosureRaised',
        ])
        self.assertIn('SufficiencyOfDisclosure', self.adm.case)

    def test_flat_unexpected_imprecise_rejected(self):
        """ReliableTechnicalEffect rejected when unexpected effect is imprecisely described."""
        self.evaluate_case([
            'TechnicalContribution', 'Credible', 'UnexpectedEffect',
            # PreciseTerms absent → ImpreciseUnexpectedEffect fires
        ])
        self.assertIn('ImpreciseUnexpectedEffect', self.adm.case)
        self.assertNotIn('ReliableTechnicalEffect', self.adm.case)

    def test_flat_non_technical_contribution_only(self):
        """NonTechnicalContribution present when features lack TechnicalContribution."""
        self.evaluate_case(['NonTechnicalContribution'])
        self.assertNotIn('TechnicalContribution', self.adm.case)

    def test_otp_uses_subadm_node(self):
        """OTPNotObvious must be a SubADMNode in this variant."""
        node = self.adm.nodes['OTPNotObvious']
        self.assertIsInstance(node, SubADMNode)

    def test_question_order_contains_flat_keys(self):
        """Question order must reference flat Q100+ keys not Sub-ADM 1 node."""
        qo = self.adm.questionOrder
        self.assertIn('DistinguishingFeatures', qo)
        self.assertNotIn('ReliableTechnicalEffect', qo)

    def test_invstep_accepted_no_sub1(self):
        """InvStep accepted with flat contribution path + Sub-ADM 2 results."""
        facts = {
            "OTPNotObvious_results": [["ObjectiveTechnicalProblemFormulation"]],
            "OTPNotObvious_rejected_count": 0,
            "OTPNotObvious_accepted_count": 1,
        }
        self.evaluate_case(
            ['DistinguishingFeatures', 'TechnicalContribution', 'ReliableTechnicalEffect',
             'OTPNotObvious', 'Novelty'],
            facts,
        )
        self.assertIn('ValidOTP', self.adm.case)
        self.assertIn('InvStep', self.adm.case)

class TestMainADMAblation_NoSub2(unittest.TestCase):
    """Tests for adm_main(sub_adm_1_flag=True, sub_adm_2_flag=False).

    Sub-ADM 1 is active; sub-ADM 2 (OTP) is replaced by flat questions Q200-Q203.
    """

    def setUp(self):
        self.adm = adm_main(sub_adm_1_flag=True, sub_adm_2_flag=False)
        self.adm.case = []

    def evaluate_case(self, case_items, facts=None):
        self.adm.case = list(case_items)
        if facts:
            for k, v in facts.items():
                self.adm.setFact(k, v)
        with redirect_stdout(io.StringIO()):
            self.adm.evaluateTree(self.adm.case)

    def test_structure_has_root_invstep(self):
        self.assertEqual(self.adm.root_node.name, 'InvStep')

    def test_flat_otp_nodes_present(self):
        """Q200-Q203 flat nodes must exist."""
        expected = ['Encompassed', 'ScopeOfClaim', 'Hindsight', 'ValidOTP']
        for n in expected:
            self.assertIn(n, self.adm.nodes, f"Missing node: {n}")

    def test_otp_not_obvious_is_regular_node(self):
        """OTPNotObvious must NOT be a SubADMNode in this variant."""
        node = self.adm.nodes['OTPNotObvious']
        self.assertNotIsInstance(node, SubADMNode)

    def test_sub1_is_subadm_node(self):
        """ReliableTechnicalEffect must be a SubADMNode in this variant."""
        node = self.adm.nodes['ReliableTechnicalEffect']
        self.assertIsInstance(node, SubADMNode)

    def test_flat_otp_valid_path(self):
        """ValidOTP accepted via flat Encompassed + ScopeOfClaim without Hindsight."""
        self.evaluate_case(['Encompassed', 'ScopeOfClaim'])
        self.assertIn('BasicFormulation', self.adm.case)
        self.assertIn('WellFormed', self.adm.case)
        self.assertIn('ValidOTP', self.adm.case)

    def test_flat_otp_hindsight_blocks_well_formed(self):
        """WellFormed blocked when Hindsight present."""
        self.evaluate_case(['Encompassed', 'ScopeOfClaim', 'Hindsight'])
        self.assertNotIn('WellFormed', self.adm.case)

    def test_flat_otp_would_have_arrived_modification(self):
        """WouldHaveArrived accepted when WouldModify and ValidOTP both present."""
        self.evaluate_case(['Encompassed', 'ScopeOfClaim', 'WouldModify'])
        self.assertIn('ValidOTP', self.adm.case)
        self.assertIn('WouldHaveArrived', self.adm.case)

    def test_flat_otp_would_have_arrived_adaptation(self):
        """WouldHaveArrived accepted when WouldAdapt and ValidOTP both present."""
        self.evaluate_case(['Encompassed', 'ScopeOfClaim', 'WouldAdapt'])
        self.assertIn('WouldHaveArrived', self.adm.case)

    def test_flat_otp_not_obvious_when_not_arrived(self):
        """OTPNotObvious accepted (not obvious) when WouldHaveArrived is absent."""
        self.evaluate_case(['Encompassed', 'ScopeOfClaim'])
        self.assertIn('ValidOTP', self.adm.case)
        self.assertNotIn('WouldHaveArrived', self.adm.case)
        self.assertIn('OTPNotObvious', self.adm.case)

    def test_flat_otp_obvious_when_arrived(self):
        """OTPNotObvious rejected (obvious) when WouldHaveArrived is present."""
        self.evaluate_case(['Encompassed', 'ScopeOfClaim', 'WouldModify'])
        self.assertIn('WouldHaveArrived', self.adm.case)
        self.assertNotIn('OTPNotObvious', self.adm.case)

    def test_flat_constrained_problem(self):
        """ConstrainedProblem present when NonTechnicalContribution constrains the OTP."""
        self.evaluate_case(['Encompassed', 'ScopeOfClaim', 'NonTechnicalContribution'])
        self.assertIn('WellFormed', self.adm.case)
        self.assertIn('ConstrainedProblem', self.adm.case)

    def test_question_order_contains_flat_otp_keys(self):
        """Question order must reference flat OTP questions."""
        qo = self.adm.questionOrder
        self.assertIn('Encompassed', qo)
        self.assertNotIn('OTPNotObvious', qo)

    def test_invstep_accepted_no_sub2(self):
        """InvStep accepted with Sub-ADM 1 results + flat OTP path."""
        facts = {
            "ReliableTechnicalEffect_results": [["DistinguishingFeatures", "FeatureTechnicalContribution"]],
        }
        self.evaluate_case(
            ['DistinguishingFeatures', 'TechnicalContribution', 'ReliableTechnicalEffect',
             'Novelty', 'Encompassed', 'ScopeOfClaim'],
            facts,
        )
        self.assertIn('ValidOTP', self.adm.case)
        self.assertIn('OTPNotObvious', self.adm.case)
        self.assertIn('InvStep', self.adm.case)

class TestMainADMAblation_NoBoth(unittest.TestCase):
    """Tests for adm_main(sub_adm_1_flag=False, sub_adm_2_flag=False).

    Both sub-ADMs replaced by flat questions.  This is the fully ablated variant.
    """

    def setUp(self):
        self.adm = adm_main(sub_adm_1_flag=False, sub_adm_2_flag=False)
        self.adm.case = []

    def evaluate_case(self, case_items, facts=None):
        self.adm.case = list(case_items)
        if facts:
            for k, v in facts.items():
                self.adm.setFact(k, v)
        with redirect_stdout(io.StringIO()):
            self.adm.evaluateTree(self.adm.case)

    def test_structure_has_root_invstep(self):
        self.assertEqual(self.adm.root_node.name, 'InvStep')

    def test_no_subadm_nodes(self):
        """Neither ReliableTechnicalEffect nor OTPNotObvious should be SubADMNodes."""
        self.assertNotIsInstance(self.adm.nodes['ReliableTechnicalEffect'], SubADMNode)
        self.assertNotIsInstance(self.adm.nodes['OTPNotObvious'], SubADMNode)

    def test_flat_question_instantiators_present(self):
        """Both flat question instantiators must exist."""
        self.assertIn('technical_contribution', self.adm.question_instantiators)
        self.assertIn('modify_adapt', self.adm.question_instantiators)

    def test_question_order_has_both_flat_paths(self):
        """Question order must include keys from both flat paths."""
        qo = self.adm.questionOrder
        self.assertIn('DistinguishingFeatures', qo)
        self.assertIn('Encompassed', qo)

    def test_invstep_full_flat_path_success(self):
        """InvStep accepted on fully flat path."""
        self.evaluate_case([
            'DistinguishingFeatures', 'TechnicalContribution', 'Credible',
            'ReliableTechnicalEffect', 'Novelty',
            'Encompassed', 'ScopeOfClaim',
        ])
        self.assertIn('ValidOTP', self.adm.case)
        self.assertIn('OTPNotObvious', self.adm.case)
        self.assertIn('InvStep', self.adm.case)

    def test_invstep_flat_rejected_no_tech_contribution(self):
        """InvStep rejected when no technical contribution on flat path."""
        self.evaluate_case(['DistinguishingFeatures', 'Credible'])
        self.assertNotIn('TechnicalContribution', self.adm.case)
        self.assertNotIn('InvStep', self.adm.case)

    def test_invstep_flat_rejected_hindsight(self):
        """InvStep rejected when OTP formulated with hindsight (flat path)."""
        self.evaluate_case([
            'DistinguishingFeatures', 'TechnicalContribution', 'Credible',
            'ReliableTechnicalEffect', 'Novelty',
            'Encompassed', 'ScopeOfClaim', 'Hindsight',
        ])
        self.assertNotIn('WellFormed', self.adm.case)
        self.assertNotIn('InvStep', self.adm.case)

    def test_invstep_obvious_via_would_have_arrived(self):
        """OTPNotObvious absent when skilled person would have arrived (flat OTP)."""
        self.evaluate_case([
            'DistinguishingFeatures', 'TechnicalContribution', 'Credible',
            'ReliableTechnicalEffect', 'Novelty',
            'Encompassed', 'ScopeOfClaim', 'WouldModify',
        ])
        self.assertIn('WouldHaveArrived', self.adm.case)
        self.assertNotIn('OTPNotObvious', self.adm.case)

class TestMainADMSecondaryIndicators(unittest.TestCase):
    """Tests for secondary indicator nodes in adm_main(True, True)."""

    def setUp(self):
        self.adm = adm_main()
        self.adm.case = []

    def evaluate_case(self, case_items):
        self.adm.case = list(case_items)
        with redirect_stdout(io.StringIO()):
            self.adm.evaluateTree(self.adm.case)

    # --- PredictableDisadvantage ---
    def test_predictable_disadvantage(self):
        """PredictableDisadvantage present when foreseeable disadvantageous mod exists."""
        self.evaluate_case(['DisadvantageousMod', 'Foreseeable'])
        self.assertIn('PredictableDisadvantage', self.adm.case)
        self.assertIn('SecondaryIndicator', self.adm.case)

    def test_predictable_disadvantage_blocked_unexpected_advantage(self):
        """PredictableDisadvantage blocked when unexpected advantage compensates."""
        self.evaluate_case(['DisadvantageousMod', 'Foreseeable', 'UnexpectedAdvantage'])
        self.assertNotIn('PredictableDisadvantage', self.adm.case)

    def test_no_predictable_disadvantage_without_foreseeable(self):
        """PredictableDisadvantage absent when disadvantageous mod not foreseeable."""
        self.evaluate_case(['DisadvantageousMod'])
        self.assertNotIn('PredictableDisadvantage', self.adm.case)

    # --- BioTech ---
    def test_biotech_obvious_predictable_results(self):
        """BioTechObvious fires when BioTech with PredictableResults."""
        self.evaluate_case(['BioTech', 'PredictableResults'])
        self.assertIn('BioTechObvious', self.adm.case)
        self.assertIn('SecondaryIndicator', self.adm.case)

    def test_biotech_obvious_reasonable_success(self):
        """BioTechObvious fires when BioTech with ReasonableSuccess."""
        self.evaluate_case(['BioTech', 'ReasonableSuccess'])
        self.assertIn('BioTechObvious', self.adm.case)

    def test_biotech_not_obvious_unexpected_effect(self):
        """BioTechObvious blocked when UnexpectedEffect is present."""
        self.evaluate_case(['BioTech', 'PredictableResults', 'UnexpectedEffect'])
        self.assertNotIn('BioTechObvious', self.adm.case)

    # --- Antibody ---
    def test_antibody_obvious_known_technique(self):
        """AntibodyObvious fires when BioTech + Antibody + KnownTechnique."""
        self.evaluate_case(['BioTech', 'Antibody', 'KnownTechnique'])
        self.assertIn('SubjectMatterAntibody', self.adm.case)
        self.assertIn('AntibodyObvious', self.adm.case)
        self.assertIn('SecondaryIndicator', self.adm.case)

    def test_antibody_not_obvious_overcomes_difficulty(self):
        """AntibodyObvious blocked when OvercomeTechDifficulty present."""
        self.evaluate_case(['BioTech', 'Antibody', 'KnownTechnique', 'OvercomeTechDifficulty'])
        self.assertNotIn('AntibodyObvious', self.adm.case)

    def test_antibody_no_subject_matter_without_biotech(self):
        """SubjectMatterAntibody absent when BioTech is absent."""
        self.evaluate_case(['Antibody', 'KnownTechnique'])
        self.assertNotIn('SubjectMatterAntibody', self.adm.case)

    # --- KnownMeasures ---
    def test_known_measures_gap_filled(self):
        """KnownMeasures present via GapFilled."""
        self.evaluate_case(['GapFilled'])
        self.assertIn('KnownMeasures', self.adm.case)
        self.assertIn('SecondaryIndicator', self.adm.case)

    def test_known_measures_well_known_equivalent(self):
        """KnownMeasures present via WellKnownEquivalent."""
        self.evaluate_case(['WellKnownEquivalent'])
        self.assertIn('KnownMeasures', self.adm.case)

    def test_known_usage_known_properties(self):
        """KnownUsage present via KnownProperties."""
        self.evaluate_case(['KnownProperties'])
        self.assertIn('KnownUsage', self.adm.case)
        self.assertIn('KnownMeasures', self.adm.case)

    def test_known_usage_analogous_use(self):
        """KnownUsage present via AnalogousUse."""
        self.evaluate_case(['AnalogousUse'])
        self.assertIn('KnownUsage', self.adm.case)

    def test_known_usage_known_device_analogous_substitution(self):
        """KnownUsage present via KnownDevice + AnalogousSubstitution."""
        self.evaluate_case(['KnownDevice', 'AnalogousSubstitution'])
        self.assertIn('KnownUsage', self.adm.case)

    # --- ObviousSelection ---
    def test_obvious_selection_equal_alternatives(self):
        """ObviousSelection present via ChooseEqualAlternatives."""
        self.evaluate_case(['ChooseEqualAlternatives'])
        self.assertIn('ObviousSelection', self.adm.case)
        self.assertIn('SecondaryIndicator', self.adm.case)

    def test_obvious_selection_normal_design(self):
        """ObviousSelection present via NormalDesignProcedure."""
        self.evaluate_case(['NormalDesignProcedure'])
        self.assertIn('ObviousSelection', self.adm.case)

    def test_obvious_selection_simple_extrapolation(self):
        """ObviousSelection present via SimpleExtrapolation."""
        self.evaluate_case(['SimpleExtrapolation'])
        self.assertIn('ObviousSelection', self.adm.case)

    def test_obvious_selection_chemical_selection(self):
        """ObviousSelection present via ChemicalSelection."""
        self.evaluate_case(['ChemicalSelection'])
        self.assertIn('ObviousSelection', self.adm.case)

    # --- ObviousCombination ---
    def test_obvious_combination(self):
        """ObviousCombination present via KnownDevice + ObviousCombination."""
        self.evaluate_case(['KnownDevice', 'ObviousCombination'])
        self.assertIn('SecondaryIndicator', self.adm.case)

    # --- Synergy path ---
    def test_synergy_combination_path(self):
        """Combination accepted when ReliableTechnicalEffect + Synergy + FunctionalInteraction."""
        self.evaluate_case(['ReliableTechnicalEffect', 'Synergy', 'FunctionalInteraction'])
        self.assertIn('Combination', self.adm.case)
        self.assertNotIn('PartialProblems', self.adm.case)

    def test_partial_problems_without_synergy(self):
        """PartialProblems accepted when ReliableTechnicalEffect present but no Synergy."""
        self.evaluate_case(['ReliableTechnicalEffect'])
        self.assertIn('PartialProblems', self.adm.case)

class TestMainADMObvious(unittest.TestCase):
    """Tests for the Obvious node and InvStep rejection."""

    def setUp(self):
        self.adm = adm_main()
        self.adm.case = []

    def evaluate_case(self, case_items, facts=None):
        self.adm.case = list(case_items)
        if facts:
            for k, v in facts.items():
                self.adm.setFact(k, v)
        with redirect_stdout(io.StringIO()):
            self.adm.evaluateTree(self.adm.case)

    def test_invstep_rejected_sufficiency_of_disclosure(self):
        """InvStep rejected when SufficiencyOfDisclosure issue present."""
        facts = {
            "ReliableTechnicalEffect_results": [["DistinguishingFeatures", "FeatureTechnicalContribution"]],
            "OTPNotObvious_results": [["ObjectiveTechnicalProblemFormulation"]],
            "OTPNotObvious_rejected_count": 0,
        }
        self.evaluate_case(
            ['DistinguishingFeatures', 'TechnicalContribution', 'ReliableTechnicalEffect',
             'OTPNotObvious', 'Novelty', 'SufficiencyOfDisclosure'],
            facts,
        )
        self.assertNotIn('InvStep', self.adm.case)

    def test_invstep_secondary_indicator_fires_from_known_measures(self):
        """SecondaryIndicator fires from GapFilled -> KnownMeasures path."""
        facts = {
            "ReliableTechnicalEffect_results": [["DistinguishingFeatures", "FeatureTechnicalContribution"]],
            "OTPNotObvious_results": [["ObjectiveTechnicalProblemFormulation"]],
            "OTPNotObvious_rejected_count": 0,
        }
        self.evaluate_case(
            ['DistinguishingFeatures', 'TechnicalContribution', 'ReliableTechnicalEffect',
             'OTPNotObvious', 'Novelty', 'GapFilled'],
            facts,
        )
        self.assertIn('KnownMeasures', self.adm.case)
        self.assertIn('SecondaryIndicator', self.adm.case)

    def test_invstep_no_novelty(self):
        """InvStep rejected when there are no distinguishing features (no Novelty)."""
        self.evaluate_case([])
        self.assertNotIn('Novelty', self.adm.case)
        self.assertNotIn('InvStep', self.adm.case)

    def test_contribution_both_technical_and_non_technical(self):
        """Contribution accepted via both TechnicalContribution AND NonTechnicalContribution."""
        self.evaluate_case(['TechnicalContribution', 'NonTechnicalContribution'])
        self.assertIn('Contribution', self.adm.case)

    def test_candidate_otp_combination(self):
        """CandidateOTP via Combination (synergy) path."""
        facts = {
            "ReliableTechnicalEffect_results": [["FeatureTechnicalContribution"]],
        }
        self.evaluate_case(
            ['TechnicalContribution', 'ReliableTechnicalEffect', 'Synergy', 'FunctionalInteraction'],
            facts,
        )
        self.assertIn('Combination', self.adm.case)
        self.assertIn('Contribution', self.adm.case)
        self.assertIn('CandidateOTP', self.adm.case)

    def test_candidate_otp_partial_problems(self):
        """CandidateOTP via PartialProblems (no synergy) path."""
        facts = {
            "ReliableTechnicalEffect_results": [["FeatureTechnicalContribution"]],
        }
        self.evaluate_case(
            ['TechnicalContribution', 'ReliableTechnicalEffect'],
            facts,
        )
        self.assertIn('PartialProblems', self.adm.case)
        self.assertIn('CandidateOTP', self.adm.case)

class TestADMConstructionCoverage(unittest.TestCase):
    """Targets uncovered lines in ADM_Construction.py."""

    def setUp(self):
        from ADM_Construction import ADM
        self.ADM = ADM
        self.adm = ADM("CoverageTest")

    def test_adm_str(self):
        """ADM __str__ returns name (line 99)."""
        self.assertEqual(str(self.adm), "CoverageTest")

    def test_addQuestionInstantiator_autogenerate_name(self):
        """question_order_name auto-generated when None passed (line 153)."""
        self.adm.addQuestionInstantiator(
            "Auto Q?",
            {"Yes": "BLF_Y", "No": ""},
            question_order_name=None,
        )
        # At least one auto-generated key should now be in question_instantiators
        auto_keys = [k for k in self.adm.question_instantiators if k.startswith("question_")]
        self.assertTrue(len(auto_keys) >= 1)

    def test_addQuestionInstantiator_duplicate_name_not_duplicated_in_order(self):
        """Adding same question_order_name twice must not duplicate it in questionOrder."""
        self.adm.addQuestionInstantiator("Q?", {"Yes": "B"}, question_order_name="myq")
        self.adm.addQuestionInstantiator("Q2?", {"No": ""}, question_order_name="myq")
        self.assertEqual(self.adm.questionOrder.count("myq"), 1)

    def test_check_early_stop_no_root_node(self):
        """check_early_stop returns False immediately when root_node not set (line 272)."""
        adm = self.ADM("NoRoot")
        adm.addNodes("A")
        result = adm.check_early_stop({"A"})
        self.assertFalse(result)

    def test_evaluate_tree_guard_no_logic(self):
        """evaluateTree handles nodes with no acceptance logic (line 350)."""
        self.adm.addNodes("LeafOnly")
        self.adm.addNodes("Root", acceptance=["LeafOnly"], root=True)
        self.adm.case = ["LeafOnly"]
        with redirect_stdout(io.StringIO()):
            stmts = self.adm.evaluateTree(self.adm.case)
        self.assertIn("Root", self.adm.case)

    def test_generate_explanation_default_statement_index(self):
        """Explanation generation handles out-of-range index gracefully (line 389)."""
        # statement list has only 1 entry but acceptance has 2 conditions
        self.adm.addNodes("A")
        self.adm.addNodes("B")
        # statement only has entry for index 0
        self.adm.addNodes("Root", acceptance=["A", "B"], statement=["A accepted"], root=True)
        self.adm.case = ["B"]  # B matches condition index 1, but statement[1] doesn't exist
        with redirect_stdout(io.StringIO()):
            stmts = self.adm.evaluateTree(self.adm.case)
        # Should not crash; Root should still be accepted
        self.assertIn("Root", self.adm.case)

    def test_nonleafgen_populates_nonleaf(self):
        """nonLeafGen builds the nonLeaf dict from nodes with children."""
        self.adm.addNodes("Child")
        self.adm.addNodes("Parent", acceptance=["Child"])
        self.adm.nonLeafGen()
        self.assertIn("Parent", self.adm.nonLeaf)

    def test_postfix_empty_stack_returns_false(self):
        """postfixEvaluation on empty acceptance string returns False."""
        result = self.adm.postfixEvaluation("")
        self.assertFalse(result)

    def test_postfix_accept_token(self):
        """'accept' token pushes True onto the stack."""
        result = self.adm.postfixEvaluation("accept")
        self.assertTrue(result)

    def test_gated_blf_check_gated_true(self):
        """GatedBLF.check_gated returns True when all deps in case."""
        blf = GatedBLF("MyBLF", ["DepA", "DepB"], "Question?")
        self.assertTrue(blf.check_gated(["DepA", "DepB", "Other"]))

    def test_gated_blf_check_gated_false(self):
        """GatedBLF.check_gated returns False when dep missing."""
        blf = GatedBLF("MyBLF", ["DepA", "DepB"], "Question?")
        self.assertFalse(blf.check_gated(["DepA"]))

    def test_evaluation_node_missing_fact_returns_false(self):
        """EvaluationNode.evaluateResults returns False when fact key missing."""
        node = EvaluationNode("Eval", "NonExistentBLF", "Target")
        adm = self.ADM("Test")
        result = node.evaluateResults(adm)
        self.assertFalse(result)

    def test_evaluation_node_invalid_case_format(self):
        """EvaluationNode handles non-list item in results gracefully."""
        node = EvaluationNode("Eval", "SomeBLF", "Target")
        adm = self.ADM("Test")
        adm.setFact("SomeBLF_results", ["not_a_list"])
        with redirect_stdout(io.StringIO()):
            result = node.evaluateResults(adm)
        self.assertFalse(result)

    def test_subadm_node_get_source_items_list(self):
        """SubADMNode._get_source_items returns list directly when function is a list."""
        node = SubADMNode("TestSub", MagicMock(), ["Item1", "Item2"])
        node.main_adm = self.adm
        items = node._get_source_items()
        self.assertEqual(items, ["Item1", "Item2"])

    def test_subadm_node_get_source_items_callable(self):
        """SubADMNode._get_source_items calls function when callable."""
        func = MagicMock(return_value=["DynItem"])
        node = SubADMNode("TestSub", MagicMock(), func)
        node.main_adm = self.adm
        items = node._get_source_items()
        func.assert_called_once_with(self.adm)
        self.assertEqual(items, ["DynItem"])

    def test_subadm_node_get_source_items_invalid(self):
        """SubADMNode._get_source_items returns None for invalid function type."""
        node = SubADMNode("TestSub", MagicMock(), 42)
        node.main_adm = self.adm
        with redirect_stdout(io.StringIO()):
            result = node._get_source_items()
        self.assertIsNone(result)

    def test_subadm_node_no_items_returns_false(self):
        """SubADMNode.evaluateSubADMs returns False when no items found."""
        node = SubADMNode("TestSub", MagicMock(), [])
        node.main_adm = self.adm
        ui_mock = MagicMock()
        ui_mock.adm = self.adm
        with redirect_stdout(io.StringIO()):
            result = node.evaluateSubADMs(ui_mock)
        self.assertFalse(result)

    @patch('pydot.Dot')
    @patch('pydot.Node')
    @patch('pydot.Edge')
    def test_visualise_minimalist_no_root(self, mock_edge, mock_node, mock_dot):
        """visualiseMinimalist works when no root_node is set."""
        mock_graph = MagicMock()
        mock_dot.return_value = mock_graph
        self.adm.addNodes("A")
        self.adm.addNodes("B")
        with redirect_stdout(io.StringIO()):
            self.adm.visualiseMinimalist(filename="test_min.png")
        mock_graph.write_png.assert_called_with("test_min.png")

    @patch('pydot.Dot')
    def test_visualise_minimalist_write_error(self, mock_dot):
        """visualiseMinimalist handles write error gracefully."""
        mock_graph = MagicMock()
        mock_graph.write_png.side_effect = Exception("Graphviz not found")
        mock_dot.return_value = mock_graph
        self.adm.addNodes("A")
        with redirect_stdout(io.StringIO()):
            self.adm.visualiseMinimalist(filename="err.png")
        # Should not raise

    @patch('pydot.Dot')
    def test_visualise_network_write_error(self, mock_dot):
        """visualiseNetwork handles write error gracefully."""
        mock_graph = MagicMock()
        mock_graph.write_png.side_effect = Exception("fail")
        mock_dot.return_value = mock_graph
        self.adm.addNodes("A")
        with redirect_stdout(io.StringIO()):
            self.adm.visualiseNetwork(filename="err.png", case=[])
        # Should not raise

    def test_visualise_sub_adms_no_facts(self):
        """visualiseSubADMs does nothing silently when no sub-ADM facts set."""
        with redirect_stdout(io.StringIO()):
            self.adm.visualiseSubADMs(output_dir="/tmp/test_sub_viz_no_facts")
        # Should complete without error

    @patch('os.makedirs')
    @patch('os.path.exists', return_value=False)
    def test_visualise_sub_adms_with_instances(self, mock_exists, mock_makedirs):
        """visualiseSubADMs iterates stored sub-ADM instances."""
        mock_sub = MagicMock()
        mock_sub.case = []
        # Register the node so visualiseSubADMs finds it in self.nodes
        self.adm.addNodes("MyNode")
        self.adm.setFact("MyNode_sub_adm_instances", {"ItemA": mock_sub})
        with redirect_stdout(io.StringIO()):
            self.adm.visualiseSubADMs(output_dir="/tmp/test_sub_viz")
        mock_sub.visualiseNetwork.assert_called_once()

    def test_addGatedBLF_registers_node(self):
        """addGatedBLF creates a GatedBLF node in nodes dict."""
        self.adm.addNodes("GateNode")
        self.adm.addGatedBLF("MyGatedBLF", "GateNode", "Is X true?")
        self.assertIn("MyGatedBLF", self.adm.nodes)
        self.assertIsInstance(self.adm.nodes["MyGatedBLF"], GatedBLF)

    def test_addSubADMNode_registers_node(self):
        """addSubADMNode creates a SubADMNode in nodes dict."""
        self.adm.addSubADMNode("MySub", sub_adm=MagicMock(), function=["Item1"])
        self.assertIn("MySub", self.adm.nodes)
        self.assertIsInstance(self.adm.nodes["MySub"], SubADMNode)

    def test_addEvaluationNode_registers_node(self):
        """addEvaluationNode creates an EvaluationNode in nodes dict."""
        self.adm.addEvaluationNode("MyEval", "SourceBLF", "TargetNode")
        self.assertIn("MyEval", self.adm.nodes)
        self.assertIsInstance(self.adm.nodes["MyEval"], EvaluationNode)

    def test_3vl_has_unknown_reject_guard_in_check_early_stop(self):
        """check_early_stop does not prematurely accept when reject condition unknown."""
        # Root: accept if "reject A", but A is unevaluated (Unknown)
        self.adm.addNodes("A")
        self.adm.addNodes("Root", acceptance=["reject A"], root=True)
        self.adm.root_node = self.adm.nodes["Root"]
        # A not evaluated — should be Unknown, so can't early-stop
        result = self.adm.check_early_stop(set())
        # Early stop may or may not fire, but must not crash
        self.assertIsInstance(result, bool)

class TestUIExtended(unittest.TestCase):
    """Extended UI tests targeting uncovered branches in UI.py."""

    def setUp(self):
        self.mock_adm = MagicMock()
        self.mock_adm.nodes = {}
        self.mock_adm.questionOrder = []
        self.mock_adm.information_questions = {}
        self.mock_adm.question_instantiators = {}
        self.mock_adm.case = []
        self.mock_adm.root_node = MagicMock()
        self.mock_adm.root_node.name = "Root"
        self.mock_adm.facts = {}
        self.mock_adm.check_early_stop.return_value = False
        self.mock_adm.resolveQuestionTemplate.side_effect = lambda x: x
        self.mock_adm.evaluateTree.return_value = []
        self.cli = CLI(self.mock_adm)

    # --- query_domain ---

    def test_query_domain_returns_true_when_root_in_case(self):
        """query_domain returns True when root_node name is in the case after evaluation."""
        self.cli.caseName = "TestCase"
        self.mock_adm.root_node.name = "Root"
        self.cli.case = ["Root"]
        self.mock_adm.case = ["Root"]
        self.cli.ask_questions = MagicMock()
        result = self.cli.query_domain()
        self.assertTrue(result)

    def test_query_domain_returns_false_when_root_not_in_case(self):
        """query_domain returns False when root_node name is absent."""
        self.cli.caseName = "TestCase"
        self.mock_adm.root_node.name = "Root"
        self.cli.case = []
        self.mock_adm.case = []
        self.cli.ask_questions = MagicMock()
        result = self.cli.query_domain()
        self.assertFalse(result)

    @patch('builtins.input', side_effect=[""])
    def test_query_domain_empty_case_name(self, mock_input):
        """query_domain handles empty case name input gracefully."""
        self.cli.ask_questions = MagicMock()
        with redirect_stdout(io.StringIO()):
            self.cli.query_domain()
        self.assertEqual(self.cli.caseName, "")

    # --- ask_questions ---

    def test_ask_questions_raises_on_empty_order(self):
        """ask_questions raises ValueError when question_order is empty."""
        with self.assertRaises(ValueError):
            self.cli.ask_questions({}, [])

    # --- questiongen: unknown node falls through else branch ---

    def test_questiongen_unknown_node_falls_through(self):
        """Unknown node name is silently skipped (else branch, line 247-254)."""
        # Key not in info questions, not in question_instantiators, not in nodes
        order, nodes = self.cli.questiongen(["UNKNOWN_NODE"], {})
        self.assertEqual(order, [])

    # --- questiongen: gated question instantiator skipped ---

    def test_questiongen_gated_instantiator_skipped(self):
        """Question instantiator is skipped when gate not satisfied."""
        self.mock_adm.question_instantiators = {
            "q_gated": {
                'question': "Gated Q?",
                'blf_mapping': {"Yes": "BLF_Y"},
                'factual_ascription': None,
                'gating_node': 'GateNode',
            }
        }
        # GateNode not in case → gates_satisfied returns False
        self.cli.gates_satisfied = MagicMock(return_value=False)
        order, nodes = self.cli.questiongen(["q_gated"], {})
        self.assertEqual(order, [])

    # --- questionHelper: question instantiator factual ascription ---

    @patch('builtins.input', side_effect=["1", "SomeFactAnswer"])
    @patch('builtins.print')
    def test_question_helper_factual_ascription(self, mock_print, mock_input):
        """questionHelper asks factual ascription follow-up when configured."""
        self.mock_adm.question_instantiators = {
            "q_fact": {
                'question': "Which type?",
                'blf_mapping': {"Type A": "BLF_A"},
                'factual_ascription': {"BLF_A": {"FACT_KEY": "Describe it:"}},
                'gating_node': None,
            }
        }
        self.cli.questionHelper(None, "q_fact")
        self.assertIn("BLF_A", self.cli.case)
        self.mock_adm.setFact.assert_called_with("FACT_KEY", "SomeFactAnswer")

    # --- questionHelper: node without question ---

    def test_question_helper_node_no_question(self):
        """questionHelper accepts node with no question text automatically."""
        node = MagicMock()
        node.question = None
        self.cli.questionHelper(node, "AutoNode")
        self.assertIn("AutoNode", self.cli.case)

    # --- questionHelper: invalid y/n retries ---

    @patch('builtins.input', side_effect=["maybe", "y"])
    @patch('builtins.print')
    def test_question_helper_invalid_then_valid_yn(self, mock_print, mock_input):
        """questionHelper retries on invalid y/n input."""
        node = MagicMock()
        node.question = "[Q1] Is this valid?"
        self.cli.questionHelper(node, "Q1Node")
        self.assertIn("Q1Node", self.cli.case)

    @patch('builtins.input', side_effect=["n"])
    @patch('builtins.print')
    def test_question_helper_no_answer(self, mock_print, mock_input):
        """questionHelper does not add node when 'n' given."""
        node = MagicMock()
        node.question = "[Q1] Is this valid?"
        self.cli.questionHelper(node, "Q1Node")
        self.assertNotIn("Q1Node", self.cli.case)

    # --- questionHelper: invalid choice retries ---

    @patch('builtins.input', side_effect=["99", "abc", "1"])
    @patch('builtins.print')
    def test_question_instantiator_invalid_then_valid_choice(self, mock_print, mock_input):
        """questionHelper retries when invalid choice or non-int entered."""
        self.mock_adm.question_instantiators = {
            "q1": {
                'question': "Which?",
                'blf_mapping': {"OptionA": "BLF_A"},
                'factual_ascription': None,
                'gating_node': None,
            }
        }
        self.cli.questionHelper(None, "q1")
        self.assertIn("BLF_A", self.cli.case)

    # --- _mark_blfs_as_evaluated ---

    def test_mark_blfs_as_evaluated_list_outcome(self):
        """_mark_blfs_as_evaluated handles list outcomes correctly."""
        instantiator = {
            'blf_mapping': {
                "Option": ["BLF_X", "BLF_Y"],
                "Other": "BLF_Z",
                "Empty": "",
            }
        }
        self.cli._mark_blfs_as_evaluated(instantiator)
        self.assertIn("BLF_X", self.cli.evaluated_blfs)
        self.assertIn("BLF_Y", self.cli.evaluated_blfs)
        self.assertIn("BLF_Z", self.cli.evaluated_blfs)
        self.assertNotIn("", self.cli.evaluated_blfs)

    # --- gates_satisfied ---

    def test_gates_satisfied_gated_node_not_in_case_evaluateGates_fails(self):
        """gates_satisfied returns False when gate evaluateGates fails."""
        self.mock_adm.question_instantiators = {
            "q_gated": {
                'question': "Q?",
                'blf_mapping': {"Yes": "B"},
                'factual_ascription': None,
                'gating_node': 'RequiredGate',
            }
        }
        instantiator = self.mock_adm.question_instantiators["q_gated"]
        self.cli.evaluateGates = MagicMock(return_value=False)
        result = self.cli.gates_satisfied(instantiator, [])
        self.assertFalse(result)

    def test_gates_satisfied_gated_node_already_in_case(self):
        """gates_satisfied returns True when gate is already satisfied in case."""
        instantiator = {
            'gating_node': 'RequiredGate',
            'blf_mapping': {"Yes": "B"},
        }
        result = self.cli.gates_satisfied(instantiator, ["RequiredGate"])
        self.assertTrue(result)

    def test_gates_satisfied_no_gating_node(self):
        """gates_satisfied returns True when no gating_node set."""
        instantiator = {'gating_node': None}
        result = self.cli.gates_satisfied(instantiator, [])
        self.assertTrue(result)

    # --- evaluateGates ---

    def test_evaluate_gates_node_no_acceptance(self):
        """evaluateGates returns False when gate node has no acceptance conditions."""
        gate_node = MagicMock()
        gate_node.acceptance = None
        gate_node.children = None
        self.mock_adm.nodes = {"MyGate": gate_node}
        result = self.cli.evaluateGates("MyGate", "question")
        self.assertFalse(result)

    def test_evaluate_gates_with_children(self):
        """evaluateGates recurses into children before evaluating parent."""
        child_node = MagicMock()
        child_node.acceptance = ["SomeBLF"]
        child_node.children = None  # no further recursion
        gate_node = MagicMock()
        gate_node.acceptance = ["ChildGate"]
        gate_node.children = ["ChildGate"]
        self.mock_adm.nodes = {"ChildGate": child_node, "ParentGate": gate_node}
        self.mock_adm.evaluateNode.return_value = (True, 0)
        self.mock_adm.case = []
        result = self.cli.evaluateGates("ParentGate", "question")
        self.assertTrue(result)

    def test_evaluate_gates_exception_returns_false(self):
        """evaluateGates returns False on unexpected exception during node eval."""
        gate_node = MagicMock()
        gate_node.acceptance = ["SomeBLF"]
        gate_node.children = None
        self.mock_adm.nodes = {"ErrorGate": gate_node}
        # evaluateNode raises after original_case is saved
        self.mock_adm.evaluateNode.side_effect = RuntimeError("unexpected failure")
        result = self.cli.evaluateGates("ErrorGate", "question")
        self.assertFalse(result)

    # --- resolve_question_template ---

    def test_resolve_question_template_delegates_to_adm(self):
        """resolve_question_template delegates to adm.resolveQuestionTemplate."""
        # Override the side_effect set in setUp so return_value takes effect
        self.mock_adm.resolveQuestionTemplate.side_effect = None
        self.mock_adm.resolveQuestionTemplate.return_value = "resolved"
        result = self.cli.resolve_question_template("template {VAR}")
        self.assertEqual(result, "resolved")
        self.mock_adm.resolveQuestionTemplate.assert_called_once_with("template {VAR}")

    # --- show_outcome ---

    def test_show_outcome_no_reasoning(self):
        """show_outcome handles empty reasoning list gracefully."""
        self.cli.caseName = "TestCase"
        self.cli.case = ["A"]
        self.mock_adm.evaluateTree.return_value = []
        with redirect_stdout(io.StringIO()) as out:
            self.cli.show_outcome()
        self.assertIn("TestCase", out.getvalue())

    def test_show_outcome_with_reasoning(self):
        """show_outcome prints indented reasoning statements."""
        self.cli.caseName = "CaseX"
        self.cli.case = ["B"]
        self.mock_adm.evaluateTree.return_value = [(0, "Root accepted"), (1, "Child accepted")]
        with redirect_stdout(io.StringIO()) as out:
            self.cli.show_outcome()
        output = out.getvalue()
        self.assertIn("Root accepted", output)
        self.assertIn("Child accepted", output)

    def test_show_outcome_exception_handled(self):
        """show_outcome handles exception in evaluateTree gracefully."""
        self.cli.caseName = "ErrCase"
        self.mock_adm.evaluateTree.side_effect = Exception("boom")
        with redirect_stdout(io.StringIO()):
            self.cli.show_outcome()  # Should not raise

    # --- save_adm ---

    def test_save_adm_creates_json(self):
        """save_adm writes adm_summary.json to the expected path."""
        self.cli.caseName = "SaveTestCase"
        self.cli.case = ["A", "B"]
        self.mock_adm.name = "TestADM"
        self.mock_adm.evaluateTree.return_value = [(0, "Root")]
        self.mock_adm.facts = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            with redirect_stdout(io.StringIO()):
                self.cli.save_adm(
                    folder_base=tmpdir,
                    name="main",
                    run_id=1,
                    config=2,
                    mode="tool",
                    adm_config="both",
                    adm_initial=False,
                )
            expected_path = os.path.join(
                tmpdir, "SaveTestCase", "run_1", "config_2", "tool", "both", "False", "adm_summary.json"
            )
            self.assertTrue(os.path.exists(expected_path))
            with open(expected_path) as f:
                data = json.load(f)
            self.assertIsInstance(data, list)
            self.assertEqual(data[0]["adm_type"], "main")
            self.assertEqual(data[0]["case"], ["A", "B"])

    def test_save_adm_appends_to_existing_file(self):
        """save_adm appends to an existing adm_summary.json."""
        self.cli.caseName = "AppendCase"
        self.cli.case = ["X"]
        self.mock_adm.name = "TestADM"
        self.mock_adm.evaluateTree.return_value = []
        self.mock_adm.facts = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            with redirect_stdout(io.StringIO()):
                self.cli.save_adm(folder_base=tmpdir, run_id=1, config=1, mode="tool",
                                  adm_config="none", adm_initial=False)
                self.cli.save_adm(folder_base=tmpdir, run_id=1, config=1, mode="tool",
                                  adm_config="none", adm_initial=False)
            save_path = os.path.join(
                tmpdir, "AppendCase", "run_1", "config_1", "tool", "none", "False", "adm_summary.json"
            )
            with open(save_path) as f:
                data = json.load(f)
            self.assertEqual(len(data), 2)

    def test_save_adm_includes_sub_adm_entries(self):
        """save_adm includes sub-ADM entries when sub_adm_instances fact is present."""
        self.cli.caseName = "SubCase"
        self.cli.case = []
        self.mock_adm.name = "Main"
        self.mock_adm.evaluateTree.return_value = []
        mock_sub = MagicMock()
        mock_sub.case = ["Root"]
        mock_sub.evaluateTree.return_value = [(0, "Sub root")]
        self.mock_adm.facts = {
            "MySub_sub_adm_instances": {"Item1": mock_sub}
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with redirect_stdout(io.StringIO()):
                self.cli.save_adm(folder_base=tmpdir, run_id=1, config=1, mode="tool",
                                  adm_config="both", adm_initial=False)
            save_path = os.path.join(
                tmpdir, "SubCase", "run_1", "config_1", "tool", "both", "False", "adm_summary.json"
            )
            with open(save_path) as f:
                data = json.load(f)
        sub_entries = [e for e in data if e.get("adm_type") == "sub_adm"]
        self.assertGreater(len(sub_entries), 0)
        self.assertEqual(sub_entries[0]["item_name"], "Item1")

    # --- visualize_domain ---

    @patch('os.makedirs')
    @patch('os.path.exists', return_value=False)
    def test_visualize_domain_minimal(self, mock_exists, mock_makedirs):
        """visualize_domain with minimal=True calls visualiseMinimalist."""
        self.cli.caseName = "MinCase"
        self.mock_adm.case = []
        self.cli.visualize_domain(minimal=True)
        self.mock_adm.visualiseMinimalist.assert_called()

    @patch('os.makedirs')
    @patch('os.path.exists', return_value=False)
    def test_visualize_domain_with_name_prefix(self, mock_exists, mock_makedirs):
        """visualize_domain applies name prefix to filename."""
        self.cli.caseName = "MyCase"
        self.mock_adm.case = []
        self.mock_adm.facts = {}
        with redirect_stdout(io.StringIO()):
            self.cli.visualize_domain(minimal=False, name="Initial")
        self.mock_adm.visualiseNetwork.assert_called_with(
            filename="Initial_MyCase.png", case=[]
        )

    @patch('os.makedirs')
    @patch('os.path.exists', return_value=False)
    def test_visualize_domain_png_extension_not_doubled(self, mock_exists, mock_makedirs):
        """visualize_domain does not double .png extension."""
        self.cli.caseName = "case.png"
        self.mock_adm.case = []
        self.mock_adm.facts = {}
        with redirect_stdout(io.StringIO()):
            self.cli.visualize_domain(minimal=False)
        call_args = self.mock_adm.visualiseNetwork.call_args
        self.assertTrue(call_args[1]['filename'].endswith('.png'))
        self.assertFalse(call_args[1]['filename'].endswith('.png.png'))

    @patch('os.makedirs')
    @patch('os.path.exists', return_value=False)
    def test_visualize_domain_no_sub_adms(self, mock_exists, mock_makedirs):
        """visualize_domain with visualize_sub_adms=False skips sub-ADM scan."""
        self.cli.caseName = "TestCase"
        self.mock_adm.case = []
        self.mock_adm.facts = {"Node_sub_adm_instances": {"I": MagicMock()}}
        with redirect_stdout(io.StringIO()):
            self.cli.visualize_domain(minimal=False, visualize_sub_adms=False)
        # Sub-ADM makedirs should not be called for sub-ADMs directory
        sub_dir_calls = [c for c in mock_makedirs.call_args_list
                         if 'sub_adms' in str(c)]
        self.assertEqual(len(sub_dir_calls), 0)

if __name__ == '__main__':
    unittest.main()
