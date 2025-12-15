import unittest
from unittest.mock import MagicMock, patch, ANY
import sys
import io
import logging

# Import the module to be tested
from ADM_Construction import ADM, Node, SubADMNode, EvaluationNode, GatedBLF

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
    def test_early_stop_reject_logic(self):
        """
        Test the 'reject' logic block inside check_early_stop (Line ~290).
        Scenario: Early stop should FAIL if a 'reject' condition is Unknown (None).
        """
        # Node accepts if "A" (True) unless "reject B" (Unknown)
        self.adm.addNodes("A") # Will be evaluated True
        self.adm.addNodes("B") # Will remain Unknown
        self.adm.addNodes("Root", acceptance=["A", "reject B"], root=True)
        self.adm.root_node = self.adm.nodes["Root"]
        
        # A is True, B is Unknown
        self.adm.case = ["A"]
        # 'B' is not in evaluated_nodes, so it is Unknown in 3VL
        evaluated_nodes = {"A"}
        
        # Should NOT return True (Early Stop) because B is a risk
        result = self.adm.check_early_stop(evaluated_nodes)
        self.assertFalse(result)

    def test_early_stop_exception(self):
        """Test Exception block in check_early_stop (Line ~308)"""
        # Force an error by corrupting state
        self.adm.root_node = "NotANodeObject" # This will cause evaluateNode to crash
        
        with self.assertRaises(ValueError):
            self.adm.check_early_stop([])

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
            
if __name__ == '__main__':
    unittest.main()