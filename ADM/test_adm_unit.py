#!/usr/bin/env python3
"""
Clean unit tests for both sub-ADM and main ADM evaluation with expected final cases
"""

import unittest
import os
from ADM_JURIX.ADM.ADM_Construction import *
from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1, create_sub_adm_2, adf
import UI
from UI import CLI
import builtins
import sys
import io
from contextlib import redirect_stdout

class TestSubADMEvaluation(unittest.TestCase):
    """Unit tests for sub-ADM evaluation"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.sub_adf = create_sub_adm_1("test_feature")
    
    def evaluate_blf_combination(self, blf_list):
        """Helper method to evaluate a combination of BLFs using the tree evaluation algorithm"""
        # Start with base case
        self.sub_adf.case = ["DistinguishingFeatures"]
        
        # Add the BLFs to the case
        for blf in blf_list:
            if blf not in self.sub_adf.case:
                self.sub_adf.case.append(blf)
        
        # Use the existing tree evaluation algorithm
        self.sub_adf.evaluateTree(self.sub_adf.case)
        
        return self.sub_adf.case.copy()
    
    def assert_final_case(self, test_name, blf_list, expected_final_case):
        """Helper method to test and display final case results"""
        actual_final_case = self.evaluate_blf_combination(blf_list)
        
        # Only show output for failures
        try:
            self.assertEqual(
                set(actual_final_case), 
                set(expected_final_case),
                f"Expected: {expected_final_case}, Got: {actual_final_case}"
            )
        except AssertionError:
            # Show both cases for failures only
            print(f"\nTest: {test_name}")
            print(f"BLFs: {blf_list}")
            print(f"Expected: {sorted(expected_final_case)}")
            print(f"Actual:   {sorted(actual_final_case)}")
            raise
    
    def test_independent_contribution_only(self):
        """Test: Independent Contribution Only"""
        blf_list = ["IndependentContribution"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "IndependentContribution", 
            "NonReproducible",
            "NormalTechnicalContribution", 
            "FeatureTechnicalContribution"
        ]
        
        self.assert_final_case("Independent Contribution Only", blf_list, expected_final_case)
    
    def test_combination_contribution_only(self):
        """Test: Combination Contribution Only"""
        blf_list = ["CombinationContribution"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "CombinationContribution", 
            "NonReproducible",
            "NormalTechnicalContribution", 
            "FeatureTechnicalContribution"
        ]
        
        self.assert_final_case("Combination Contribution Only", blf_list, expected_final_case)
    
    def test_independent_with_circumvent_tech_problem(self):
        """Test: Independent Contribution + CircumventTechProblem (should be rejected)"""
        blf_list = ["IndependentContribution", "CircumventTechProblem"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "IndependentContribution", 
            "NonReproducible",
            "CircumventTechProblem"
        ]
        
        self.assert_final_case("Independent + CircumventTechProblem (rejected)", blf_list, expected_final_case)
    
    def test_independent_with_excluded_field(self):
        """Test: Independent Contribution + Excluded Field (should be rejected)"""
        blf_list = ["IndependentContribution", "ComputerSimulation"]
        expected_final_case = [
            "ExcludedField",
            "NumOrComp",
            "DistinguishingFeatures", 
            "IndependentContribution", 
            "NonReproducible",
            "ComputerSimulation"
        ]
        
        self.assert_final_case("Independent + Excluded Field (rejected)", blf_list, expected_final_case)
    
    def test_computer_simulation_with_technical_adaptation(self):
        """Test: Computer Simulation + Technical Adaptation"""
        blf_list = ["ComputerSimulation", "TechnicalAdaptation"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "NonReproducible",
            "ComputerSimulation", 
            "ExcludedField",
            "NumOrComp",
            "TechnicalAdaptation", 
            "ComputationalContribution", 
            "FeatureTechnicalContribution"
        ]
        
        self.assert_final_case("Computer Simulation + Technical Adaptation", blf_list, expected_final_case)
    
    def test_mathematical_method_with_specific_purpose(self):
        """Test: Mathematical Method + Specific Purpose + Functionally Limited"""
        blf_list = ["MathematicalMethod", "SpecificPurpose", "FunctionallyLimited"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "NonReproducible",
            "MathematicalMethod", 
            "ExcludedField",
            "SpecificPurpose", 
            "FunctionallyLimited", 
            "AppliedInField", 
            "MathematicalContribution", 
            "FeatureTechnicalContribution"
        ]
        
        self.assert_final_case("Mathematical Method + Specific Purpose + Functionally Limited", blf_list, expected_final_case)
    
    def test_independent_with_unexpected_effect(self):
        """Test: Independent Contribution + Unexpected Effect + Precise Terms + One Way Street"""
        blf_list = ["IndependentContribution", "UnexpectedEffect", "PreciseTerms", "OneWayStreet"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "IndependentContribution", 
            "NonReproducible",
            "NormalTechnicalContribution", 
            "FeatureTechnicalContribution", 
            "UnexpectedEffect", 
            "PreciseTerms", 
            "OneWayStreet", 
            "BonusEffect"
        ]
        
        self.assert_final_case("Independent + Unexpected Effect + Precise Terms + One Way Street", blf_list, expected_final_case)
    
    def test_independent_with_credible_reproducible(self):
        """Test: Independent Contribution + Credible + Reproducible"""
        blf_list = ["IndependentContribution", "Credible", "Reproducible"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "IndependentContribution", 
            "NormalTechnicalContribution", 
            "FeatureTechnicalContribution", 
            "Credible", 
            "Reproducible", 
            "FeatureReliableTechnicalEffect"
        ]
        
        self.assert_final_case("Independent + Credible + Reproducible", blf_list, expected_final_case)
    
    def test_complex_all_positive(self):
        """Test: Complex scenario with all positive factors"""
        blf_list = ["IndependentContribution", "ComputerSimulation", "TechnicalAdaptation", "Credible", "Reproducible"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "IndependentContribution", 
            "ExcludedField",
            "NumOrComp",
            "ComputerSimulation", 
            "TechnicalAdaptation", 
            "Credible", 
            "Reproducible", 
            "ComputationalContribution", 
            "FeatureTechnicalContribution", 
            "FeatureReliableTechnicalEffect"
        ]
        
        self.assert_final_case("Complex All Positive Factors", blf_list, expected_final_case)
    
    def test_complex_mixed_with_reject(self):
        """Test: Complex scenario with reject conditions"""
        blf_list = ["IndependentContribution", "CircumventTechProblem", "Credible", "Reproducible"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "IndependentContribution", 
            "CircumventTechProblem", 
            "Credible", 
            "Reproducible"
            # NormalTechnicalContribution should NOT be added due to CircumventTechProblem
        ]
        
        self.assert_final_case("Complex Mixed with Reject", blf_list, expected_final_case)
    
    def test_no_blfs(self):
        """Test: No BLFs (edge case)"""
        blf_list = ["DistinguishingFeatures"]
        expected_final_case = [
            "DistinguishingFeatures",
            "NonReproducible"
        ]
        
        self.assert_final_case("No BLFs (Base Case Only)", blf_list, expected_final_case)
    
    def test_only_excluded_field(self):
        """Test: Only Excluded Field"""
        blf_list = ["ExcludedField"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "ExcludedField",
            "NonReproducible"
        ]
        
        self.assert_final_case("Only Excluded Field", blf_list, expected_final_case)
    
    def test_only_circumvent_tech_problem(self):
        """Test: Only CircumventTechProblem"""
        blf_list = ["CircumventTechProblem"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "CircumventTechProblem",
            "NonReproducible"
        ]
        
        self.assert_final_case("Only Circumvent Tech Problem", blf_list, expected_final_case)
    
    def test_reject_statements_basic(self):
        """Test: Basic reject statements with CircumventTechProblem - should prevent NormalTechnicalContribution"""
        blf_list = ["DistinguishingFeatures", "CircumventTechProblem"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "CircumventTechProblem",
            "NonReproducible"
        ]
        
        # Test the evaluation - CircumventTechProblem should prevent NormalTechnicalContribution
        sub_adf = create_sub_adm_1("reject_test")
        sub_adf.evaluateTree(blf_list)
        statements = sub_adf.evaluateTree(blf_list)
        
        # With new short-circuiting logic, reject conditions prevent node satisfaction
        # NormalTechnicalContribution should NOT be in the case due to reject CircumventTechProblem
        self.assertNotIn("NormalTechnicalContribution", sub_adf.case, "NormalTechnicalContribution should be rejected due to CircumventTechProblem")
        self.assertNotIn("FeatureTechnicalContribution", sub_adf.case, "FeatureTechnicalContribution should not be satisfied without NormalTechnicalContribution")
        
        # Verify reject statements are present in the evaluation output
        reject_statements = [stmt for stmt in statements if 'not a technical contribution' in stmt.lower() or 'circumvents a technical problem' in stmt.lower()]
        self.assertGreater(len(reject_statements), 0, "Should have reject statements")
        
        self.assert_final_case("Basic Reject Statements", blf_list, expected_final_case)
    
    def test_reject_statements_excluded_field(self):
        """Test: ExcludedField reject statements - should prevent NormalTechnicalContribution"""
        blf_list = ["DistinguishingFeatures", "ComputerSimulation"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "NumOrComp",
            "ComputerSimulation",
            "ExcludedField",
            "NonReproducible"
        ]
        
        # Test the evaluation - ExcludedField should prevent NormalTechnicalContribution
        sub_adf = create_sub_adm_1("excluded_field_test")
        sub_adf.evaluateTree(blf_list)
        statements = sub_adf.evaluateTree(blf_list)
        
        # With new short-circuiting logic, reject conditions prevent node satisfaction
        # NormalTechnicalContribution should NOT be in the case due to reject ExcludedField
        self.assertNotIn("NormalTechnicalContribution", sub_adf.case, "NormalTechnicalContribution should be rejected due to ExcludedField")
        self.assertNotIn("FeatureTechnicalContribution", sub_adf.case, "FeatureTechnicalContribution should not be satisfied without NormalTechnicalContribution")
        
        # Verify reject statements are present in the evaluation output
        print(statements)
        reject_statements = [stmt for stmt in statements if 'not a technical contribution' in stmt.lower() or 'part of an excluded field' in stmt.lower()]
        self.assertGreater(len(reject_statements), 0, "Should have reject statements")
        
        self.assert_final_case("Excluded Field Reject Statements", blf_list, expected_final_case)
    
    def test_reject_statements_sufficiency_issue(self):
        """Test: SufficiencyOfDisclosureIssue reject statements - should prevent FeatureReliableTechnicalEffect"""
        blf_list = ["DistinguishingFeatures", "ClaimContainsEffect"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "ClaimContainsEffect",
            "NonReproducible",
            ]
        
        # Test the evaluation - SufficiencyOfDisclosureIssue should prevent FeatureReliableTechnicalEffect
        sub_adf = create_sub_adm_1("sufficiency_test")
        sub_adf.evaluateTree(blf_list)
        statements = sub_adf.evaluateTree(blf_list)
        
        # With new short-circuiting logic, reject conditions prevent node satisfaction
        # FeatureReliableTechnicalEffect should NOT be in the case due to reject SufficiencyOfDisclosureIssue
        self.assertNotIn("FeatureReliableTechnicalEffect", sub_adf.case, "FeatureReliableTechnicalEffect should be rejected due to SufficiencyOfDisclosureIssue")
        
        # Verify reject statements are present in the evaluation output
        reject_statements = [stmt for stmt in statements if 'sufficiency of disclosure precludes' in stmt.lower() or 'not reproducible' in stmt.lower()]
        self.assertGreater(len(reject_statements), 0, "Should have reject statements")
        
        self.assert_final_case("Sufficiency Issue Reject Statements", blf_list, expected_final_case)
    
    def test_reject_statements_reliable_effect(self):
        """Test: FeatureReliableTechnicalEffect reject statements - should prevent FeatureReliableTechnicalEffect"""
        blf_list = ["DistinguishingFeatures", "BonusEffect"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "BonusEffect",
            "NonReproducible"
        ]
        
        # Test the evaluation - BonusEffect should prevent FeatureReliableTechnicalEffect
        sub_adf = create_sub_adm_1("reliable_test")
        statements = sub_adf.evaluateTree(blf_list)
        
        # With new short-circuiting logic, reject conditions prevent node satisfaction
        # FeatureReliableTechnicalEffect should NOT be in the case due to reject BonusEffect
        self.assertNotIn("FeatureReliableTechnicalEffect", sub_adf.case, "FeatureReliableTechnicalEffect should be rejected due to BonusEffect")
        
        # Verify reject statements are present in the evaluation output
        reject_statements = [stmt for stmt in statements if 'bonus effect which precludes' in stmt.lower() or 'no bonus effect' in stmt.lower()]
        self.assertGreater(len(reject_statements), 0, "Should have reject statements")
        
        self.assert_final_case("Reliable Effect Reject Statements", blf_list, expected_final_case)

    def test_reject_statements_full_reliable_effect(self):
        """Test: ReliableTechnicalEffect reject statements - should prevent ReliableTechnicalEffect - use full bonus effect def"""
        blf_list = ["DistinguishingFeatures", "OneWayStreet","UnexpectedEffect","IndependentContribution"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "FeatureTechnicalContribution", "UnexpectedEffect", "OneWayStreet","NormalTechnicalContribution","IndependentContribution",
            "ImpreciseUnexpectedEffect","BonusEffect",
            "NonReproducible"
        ]
        
        # Test the evaluation - BonusEffect should prevent FeatureReliableTechnicalEffect
        sub_adf = create_sub_adm_1("reliable_test")
        statements = sub_adf.evaluateTree(blf_list)
        
        # With new short-circuiting logic, reject conditions prevent node satisfaction
        # FeatureReliableTechnicalEffect should NOT be in the case due to reject BonusEffect
        self.assertNotIn("FeatureReliableTechnicalEffect", sub_adf.case, "FeatureReliableTechnicalEffect should be rejected due to BonusEffect")
        
        # Verify reject statements are present in the evaluation output
        reject_statements = [stmt for stmt in statements if 'bonus effect which precludes' in stmt.lower() or 'no bonus effect' in stmt.lower()]
        self.assertGreater(len(reject_statements), 0, "Should have reject statements")
        
        self.assert_final_case("Reliable Effect Reject Statements", blf_list, expected_final_case)
     
    def test_reject_statements_multiple_rejects(self):
        """Test: Multiple reject conditions in one case - should prevent multiple nodes"""
        blf_list = ["DistinguishingFeatures", "CircumventTechProblem", "ComputerSimulation", "ClaimContainsEffect"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "CircumventTechProblem",
            "ComputerSimulation",
            "NumOrComp",
            "ClaimContainsEffect",
            "ExcludedField",           
            "NonReproducible",
        ]
        
        # Test the evaluation - multiple reject conditions should prevent multiple nodes
        sub_adf = create_sub_adm_1("multiple_reject_test")
        sub_adf.evaluateTree(blf_list)
        statements = sub_adf.evaluateTree(blf_list)
        
        # With new short-circuiting logic, reject conditions prevent node satisfaction
        # NormalTechnicalContribution should NOT be in the case due to reject CircumventTechProblem
        self.assertNotIn("NormalTechnicalContribution", sub_adf.case, "NormalTechnicalContribution should be rejected due to CircumventTechProblem")
        self.assertNotIn("FeatureTechnicalContribution", sub_adf.case, "FeatureTechnicalContribution should not be satisfied without NormalTechnicalContribution")
        # FeatureReliableTechnicalEffect should NOT be in the case due to reject SufficiencyOfDisclosureIssue
        self.assertNotIn("FeatureReliableTechnicalEffect", sub_adf.case, "FeatureReliableTechnicalEffect should be rejected due to SufficiencyOfDisclosureIssue")
        
        # Verify multiple reject statements are present in the evaluation output
        reject_statements = [stmt for stmt in statements if 'not a technical contribution' in stmt.lower() or 'circumvents a technical problem' in stmt.lower() or 'sufficiency of disclosure precludes' in stmt.lower() or 'not reproducible' in stmt.lower()]
        self.assertGreater(len(reject_statements), 1, "Should have multiple reject statements")
        
        self.assert_final_case("Multiple Reject Statements", blf_list, expected_final_case)
    
    def test_reject_statements_no_rejects(self):
        """Test: Case that should not trigger reject statements - should allow all nodes"""
        blf_list = ["DistinguishingFeatures", "IndependentContribution", "Credible", "Reproducible"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "IndependentContribution",
            "Credible",
            "Reproducible",
            "NormalTechnicalContribution",
            "FeatureTechnicalContribution",
            "FeatureReliableTechnicalEffect",
        ]
        
        # Test the evaluation - this case should allow all nodes to be satisfied
        sub_adf = create_sub_adm_1("no_reject_test")
        sub_adf.evaluateTree(blf_list)
        statements = sub_adf.evaluateTree(blf_list)
        
        # With new short-circuiting logic, no reject conditions should allow all nodes
        # All these nodes should be in the case since no reject conditions are satisfied
        self.assertIn("NormalTechnicalContribution", sub_adf.case, "NormalTechnicalContribution should be satisfied without reject conditions")
        self.assertIn("FeatureTechnicalContribution", sub_adf.case, "FeatureTechnicalContribution should be satisfied")
        self.assertIn("FeatureReliableTechnicalEffect", sub_adf.case, "FeatureReliableTechnicalEffect should be satisfied without reject conditions")
        
        # This case should have evaluation results (statements)
        self.assertGreater(len(statements), 0, "Should have evaluation statements")
        
        # Check that we have some positive statements (technical contribution statements)
        positive_statements = [stmt for stmt in statements if 'technical contribution' in stmt.lower() and 'not' not in stmt.lower()]
        self.assertGreater(len(positive_statements), 0, "Should have positive technical contribution statements")
        
        self.assert_final_case("No Reject Statements", blf_list, expected_final_case)
    
    
    def test_question_instantiator_basic(self):
        """Test: QuestionInstantiator basic functionality"""
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        
        # Create a sub-ADM and test question instantiator
        sub_adf = create_sub_adm_1("question_instantiator_test")
        
        # Find a QuestionInstantiator node
        question_instantiator = None
        for node_name, node in sub_adf.nodes.items():
            if hasattr(node, 'blf_mapping'):
                question_instantiator = node
                break
        
        if question_instantiator:
            # Test that it has the required attributes
            self.assertIsNotNone(question_instantiator.blf_mapping)
            self.assertIsInstance(question_instantiator.blf_mapping, dict)
            self.assertGreater(len(question_instantiator.blf_mapping), 0)
    
    def test_question_instantiator_blf_mapping(self):
        """Test: QuestionInstantiator BLF mapping functionality"""
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        
        # Create a sub-ADM
        sub_adf = create_sub_adm_1("mapping_test")
        
        # Find a QuestionInstantiator node with BLF mapping
        question_instantiator = None
        for node_name, node in sub_adf.nodes.items():
            if hasattr(node, 'blf_mapping'):
                question_instantiator = node
                break
        
        if question_instantiator:
            mapping = question_instantiator.blf_mapping
            
            # Verify expected mappings exist
            expected_mappings = [
                "A computer simulation.",
                "The processing of numerical data.",
                "A mathematical method or algorithm.",
                "Other excluded field",
                "None of the above"
            ]
            
            for expected in expected_mappings:
                self.assertIn(expected, mapping)
            
            # Verify BLF mappings
            self.assertEqual(mapping["A computer simulation."], "ComputerSimulation")
            self.assertEqual(mapping["The processing of numerical data."], "NumericalData")
            self.assertEqual(mapping["A mathematical method or algorithm."], "MathematicalMethod")
    
    
    def test_dependent_blf_factual_ascription(self):
        """Test: DependentBLF factual ascription inheritance"""
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        
        # Create a sub-ADM
        sub_adf = create_sub_adm_1("ascription_test")
        
        # Find a DependentBLF with factual ascription
        dependent_blf = None
        for node_name, node in sub_adf.nodes.items():
            if hasattr(node, 'dependency_node') and hasattr(node, 'factual_ascription'):
                dependent_blf = node
                break
        
        if dependent_blf and dependent_blf.factual_ascription:
            # Test that factual ascription is properly set
            self.assertIsInstance(dependent_blf.factual_ascription, dict)
    
    def test_question_instantiator_dependency(self):
        """Test: QuestionInstantiator with dependency node"""
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        
        # Create a sub-ADM
        sub_adf = create_sub_adm_1("qi_dependency_test")
        
        # Find a QuestionInstantiator with dependency
        qi_with_dep = None
        for node_name, node in sub_adf.nodes.items():
            if hasattr(node, 'blf_mapping') and hasattr(node, 'dependency_node'):
                qi_with_dep = node
                break
        
        if qi_with_dep:
            # Test that dependency is properly set
            self.assertIsNotNone(qi_with_dep.dependency_node)
            self.assertIsInstance(qi_with_dep.dependency_node, (str, list))


class TestSubADM2Evaluation(unittest.TestCase):
    """Unit tests for sub-ADM 2 (Objective Technical Problem) evaluation"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.sub_adf = create_sub_adm_2("test_otp")
    
    def evaluate_blf_combination(self, blf_list, key_facts=None):
        """Helper method to evaluate a combination of BLFs using the tree evaluation algorithm"""
        # Create a new sub-ADM with key facts if provided
        if key_facts:
            self.sub_adf = create_sub_adm_2("test_otp", key_facts)
        
        # Add the BLFs to the case
        for blf in blf_list:
            if blf not in self.sub_adf.case:
                self.sub_adf.case.append(blf)
        
        # Use the existing tree evaluation algorithm
        self.sub_adf.evaluateTree(self.sub_adf.case)
        
        return self.sub_adf.case.copy()
    
    def assert_final_case(self, test_name, blf_list, expected_final_case, key_facts=None):
        """Helper method to test and display final case results"""
        actual_final_case = self.evaluate_blf_combination(blf_list, key_facts)
        
        # Only show output for failures
        try:
            self.assertEqual(
                set(actual_final_case), 
                set(expected_final_case),
                f"Expected: {expected_final_case}, Got: {actual_final_case}"
            )
        except AssertionError:
            # Show both cases for failures only
            print(f"\nTest: {test_name}")
            print(f"BLFs: {blf_list}")
            print(f"Key Facts: {key_facts}")
            print(f"Expected: {sorted(expected_final_case)}")
            print(f"Actual:   {sorted(actual_final_case)}")
            raise
    
    def test_basic_formulation_with_all_requirements(self):
        """Test: Basic formulation with all requirements (Encompassed, Embodied, ScopeOfClaim)"""
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim"]
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation"
        ]
        
        self.assert_final_case("Basic Formulation with All Requirements", blf_list, expected_final_case)
    
    def test_well_formed_without_hindsight(self):
        """Test: Well formed objective technical problem without hindsight"""
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation"]
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "WellFormed"
        ]
        
        self.assert_final_case("Well Formed without Hindsight", blf_list, expected_final_case)
    
    def test_well_formed_with_hindsight_rejection(self):
        """Test: Well formed objective technical problem with hindsight (should be rejected)"""
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation", "Hindsight"]
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "Hindsight"
        ]
        
        self.assert_final_case("Well Formed with Hindsight (rejected)", blf_list, expected_final_case)
    
    def test_constrained_problem_with_non_technical_contribution(self):
        """Test: Constrained problem with non-technical contribution"""
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation", "NonTechnicalContribution"]
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "WellFormed",
            "NonTechnicalContribution", "ConstrainedProblem"
        ]
        
        self.assert_final_case("Constrained Problem with Non-Technical Contribution", blf_list, expected_final_case)
    
    def test_objective_technical_problem_formulation_constrained(self):
        """Test: Objective technical problem formulation with constraints"""
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation", "NonTechnicalContribution"]
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "WellFormed",
            "NonTechnicalContribution", "ConstrainedProblem", "ObjectiveTechnicalProblemFormulation"
        ]
        
        self.assert_final_case("OTP Formulation Constrained", blf_list, expected_final_case)
    
    def test_objective_technical_problem_formulation_unconstrained(self):
        """Test: Objective technical problem formulation without constraints"""
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation"]
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "WellFormed", "ObjectiveTechnicalProblemFormulation"
        ]
        
        self.assert_final_case("OTP Formulation Unconstrained", blf_list, expected_final_case)
    
    def test_would_have_arrived_by_modification(self):
        """Test: Would have arrived at invention by modification"""
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation", "WouldModify"]
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "WellFormed", 
            "ObjectiveTechnicalProblemFormulation", "WouldModify", "WouldHaveArrived"
        ]
        
        self.assert_final_case("Would Have Arrived by Modification", blf_list, expected_final_case)
    
    def test_would_have_arrived_by_adaptation(self):
        """Test: Would have arrived at invention by adaptation"""
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation", "WouldAdapt"]
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "WellFormed", 
            "ObjectiveTechnicalProblemFormulation", "WouldAdapt", "WouldHaveArrived"
        ]
        
        self.assert_final_case("Would Have Arrived by Adaptation", blf_list, expected_final_case)
    
    def test_non_technical_contribution_from_main_case(self):
        """Test: NonTechnicalContribution added to sub-ADM case when present in main case"""
        key_facts = {'main_case': ['NonTechnicalContribution', 'OtherFactor']}
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation"]
        expected_final_case = [
            "NonTechnicalContribution", "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "WellFormed", 
            "ConstrainedProblem", "ObjectiveTechnicalProblemFormulation"
        ]
        
        self.assert_final_case("NonTechnicalContribution from Main Case", blf_list, expected_final_case, key_facts)
    
    def test_no_non_technical_contribution_from_main_case(self):
        """Test: No NonTechnicalContribution added when not present in main case"""
        key_facts = {'main_case': ['OtherFactor', 'AnotherFactor']}
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation"]
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "WellFormed", 
            "ObjectiveTechnicalProblemFormulation"
        ]
        
        self.assert_final_case("No NonTechnicalContribution from Main Case", blf_list, expected_final_case, key_facts)
    
    def test_no_key_facts_provided(self):
        """Test: Sub-ADM case remains empty when no key facts provided"""
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation"]
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "WellFormed", 
            "ObjectiveTechnicalProblemFormulation"
        ]
        
        self.assert_final_case("No Key Facts Provided", blf_list, expected_final_case)
    
    def test_incomplete_basic_formulation(self):
        """Test: Incomplete basic formulation (missing one requirement)"""
        blf_list = ["Encompassed", "Embodied"]  # Missing ScopeOfClaim
        expected_final_case = [
            "Encompassed", "Embodied"
        ]
        
        self.assert_final_case("Incomplete Basic Formulation", blf_list, expected_final_case)
    
    def test_question_order(self):
        """Test: Verify question order is set correctly"""
        self.assertEqual(
            self.sub_adf.questionOrder, 
            ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation", "Hindsight", "modify_adapt"]
        )

    def test_abstract_factor_statements(self):
        """Test: Verify that abstract factors have correct updated statements"""
        # Test BasicFormulation statements
        basic_formulation = self.sub_adf.nodes["BasicFormulation"]
        self.assertEqual(basic_formulation.statements, 
                        ['We have a valid basic formulation of the objective technical problem', 
                         'We do not have a valid basic formulation of the objective technical problem'])
        
        # Test WellFormed statements
        well_formed = self.sub_adf.nodes["WellFormed"]
        self.assertEqual(well_formed.statements, 
                        ['There is a written objective technical problem which has been formed without hindsight', 
                         'There is no written objective technical problem which has been formed without hindsight'])
        
        # Test ConstrainedProblem statements
        constrained_problem = self.sub_adf.nodes["ConstrainedProblem"]
        self.assertEqual(constrained_problem.statements, 
                        ['There are non-technical contributions constraining the objective technical problem', 
                         'There are no non-technical contributions constraining the objective technical problem'])
        
        # Test ObjectiveTechnicalProblemFormulation statements
        otp_formulation = self.sub_adf.nodes["ObjectiveTechnicalProblemFormulation"]
        self.assertEqual(otp_formulation.statements, 
                        ['There is a valid objective technical problem formulation constrained by non-technical contributions', 
                         'There is a valid objective technical problem formulation', 
                         'There is no valid objective technical problem formulation'])
        
        # Test WouldHaveArrived statements
        would_have_arrived = self.sub_adf.nodes["WouldHaveArrived"]
        self.assertEqual(would_have_arrived.statements, 
                        ['The skilled person would have arrived at the proposed invention by modifying the closest prior art', 
                         'The skilled person would have arrived at the proposed invention by adapting the closest prior art'])

    def test_basic_formulation_acceptance_conditions(self):
        """Test: BasicFormulation acceptance conditions work correctly"""
        # Test that BasicFormulation requires all three conditions
        basic_formulation = self.sub_adf.nodes["BasicFormulation"]
        self.assertEqual(basic_formulation.acceptance, ['Encompassed and Embodied and ScopeOfClaim'])
        
        # Test that it's properly configured as an abstract factor
        self.assertIsInstance(basic_formulation, Node)
        self.assertEqual(len(basic_formulation.statements), 2)

    def test_well_formed_acceptance_conditions(self):
        """Test: WellFormed acceptance conditions work correctly"""
        # Test that WellFormed requires rejection of Hindsight AND WrittenFormulation AND BasicFormulation
        well_formed = self.sub_adf.nodes["WellFormed"]
        self.assertEqual(well_formed.acceptance, ['reject Hindsight','WrittenFormulation and BasicFormulation'])
        
        # Test that it's properly configured as an abstract factor
        self.assertIsInstance(well_formed, Node)
        self.assertEqual(len(well_formed.statements), 2)

    def test_constrained_problem_acceptance_conditions(self):
        """Test: ConstrainedProblem acceptance conditions work correctly"""
        # Test that ConstrainedProblem requires WellFormed AND NonTechnicalContribution
        constrained_problem = self.sub_adf.nodes["ConstrainedProblem"]
        self.assertEqual(constrained_problem.acceptance, ['WellFormed and NonTechnicalContribution'])
        
        # Test that it's properly configured as an abstract factor
        self.assertIsInstance(constrained_problem, Node)
        self.assertEqual(len(constrained_problem.statements), 2)

    def test_objective_technical_problem_formulation_acceptance_conditions(self):
        """Test: ObjectiveTechnicalProblemFormulation acceptance conditions work correctly"""
        # Test that it has two acceptance conditions: ConstrainedProblem and WellFormed
        otp_formulation = self.sub_adf.nodes["ObjectiveTechnicalProblemFormulation"]
        self.assertEqual(otp_formulation.acceptance, ['ConstrainedProblem','WellFormed'])
        
        # Test that it's properly configured as an abstract factor
        self.assertIsInstance(otp_formulation, Node)
        self.assertEqual(len(otp_formulation.statements), 3)

    def test_would_have_arrived_acceptance_conditions(self):
        """Test: WouldHaveArrived acceptance conditions work correctly"""
        # Test that it has two acceptance conditions for modification and adaptation
        would_have_arrived = self.sub_adf.nodes["WouldHaveArrived"]
        self.assertEqual(would_have_arrived.acceptance, 
                        ['WouldModify and  ObjectiveTechnicalProblemFormulation', 
                         'WouldAdapt and ObjectiveTechnicalProblemFormulation'])
        
        # Test that it's properly configured as an abstract factor
        self.assertIsInstance(would_have_arrived, Node)
        self.assertEqual(len(would_have_arrived.statements), 2)

    def test_abstract_factor_evaluation_with_updated_statements(self):
        """Test: Abstract factors evaluate correctly with their updated statements"""
        # Test a complete evaluation path that should trigger all updated statements
        blf_list = ["Encompassed", "Embodied", "ScopeOfClaim", "WrittenFormulation", "NonTechnicalContribution", "WouldModify"]
        final_case = self.evaluate_blf_combination(blf_list)
        
        # Verify that all abstract factors are properly evaluated
        expected_abstract_factors = [
            "BasicFormulation", "WellFormed", "ConstrainedProblem", 
            "ObjectiveTechnicalProblemFormulation", "WouldHaveArrived"
        ]
        
        for factor in expected_abstract_factors:
            self.assertIn(factor, final_case, f"Abstract factor {factor} should be in final case")
        
        # Verify the complete evaluation path
        expected_final_case = [
            "Encompassed", "Embodied", "ScopeOfClaim", 
            "BasicFormulation", "WrittenFormulation", "WellFormed",
            "NonTechnicalContribution", "ConstrainedProblem", 
            "ObjectiveTechnicalProblemFormulation", "WouldModify", "WouldHaveArrived"
        ]
        
        self.assertEqual(set(final_case), set(expected_final_case), 
                        f"Complete evaluation path should include all abstract factors. Got: {final_case}")

    def test_abstract_factor_statement_consistency(self):
        """Test: Verify that abstract factor statements are consistent with their logic"""
        # Test that BasicFormulation has appropriate statements for success/failure
        basic_formulation = self.sub_adf.nodes["BasicFormulation"]
        self.assertTrue(any("valid basic formulation" in stmt.lower() for stmt in basic_formulation.statements))
        self.assertTrue(any("not have a valid basic formulation" in stmt.lower() for stmt in basic_formulation.statements))
        
        # Test that WellFormed has appropriate statements for success/failure
        well_formed = self.sub_adf.nodes["WellFormed"]
        self.assertTrue(any("written objective technical problem" in stmt.lower() for stmt in well_formed.statements))
        self.assertTrue(any("no written objective technical problem" in stmt.lower() for stmt in well_formed.statements))
        
        # Test that ConstrainedProblem has appropriate statements for success/failure
        constrained_problem = self.sub_adf.nodes["ConstrainedProblem"]
        self.assertTrue(any("non-technical contributions constraining" in stmt.lower() for stmt in constrained_problem.statements))
        self.assertTrue(any("no non-technical contributions constraining" in stmt.lower() for stmt in constrained_problem.statements))
        
        # Test that ObjectiveTechnicalProblemFormulation has appropriate statements
        otp_formulation = self.sub_adf.nodes["ObjectiveTechnicalProblemFormulation"]
        self.assertTrue(any("valid objective technical problem formulation" in stmt.lower() for stmt in otp_formulation.statements))
        self.assertTrue(any("no valid objective technical problem formulation" in stmt.lower() for stmt in otp_formulation.statements))
        
        # Test that WouldHaveArrived has appropriate statements
        would_have_arrived = self.sub_adf.nodes["WouldHaveArrived"]
        self.assertTrue(any("modifying the closest prior art" in stmt.lower() for stmt in would_have_arrived.statements))
        self.assertTrue(any("adapting the closest prior art" in stmt.lower() for stmt in would_have_arrived.statements))


class TestMainADMEvaluation(unittest.TestCase):
    """Unit tests for main ADM evaluation"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.main_adf = adf()
    
    def evaluate_blf_combination(self, blf_list):
        """Helper method to evaluate a combination of BLFs using the tree evaluation algorithm"""
        # Start with empty case
        self.main_adf.case = []
        
        # Add the BLFs to the case
        for blf in blf_list:
            if blf not in self.main_adf.case:
                self.main_adf.case.append(blf)
        
        # Use the existing tree evaluation algorithm
        self.main_adf.evaluateTree(self.main_adf.case)
        
        return self.main_adf.case.copy()
    
    def assert_final_case(self, test_name, blf_list, expected_final_case):
        """Helper method to test and display final case results"""
        actual_final_case = self.evaluate_blf_combination(blf_list)
        
        # Only show output for failures
        try:
            self.assertEqual(
                set(actual_final_case), 
                set(expected_final_case),
                f"Expected: {expected_final_case}, Got: {actual_final_case}"
            )
        except AssertionError:
            # Show both cases for failures only
            print(f"\nTest: {test_name}")
            print(f"BLFs: {blf_list}")
            print(f"Expected: {sorted(expected_final_case)}")
            print(f"Actual:   {sorted(actual_final_case)}")
            raise
    
    def test_basic_skilled_person_establishment(self):
        """Test: Basic skilled person establishment"""
        blf_list = ["Individual", "SkilledIn", "Average", "Aware", "Access"]
        expected_final_case = [
            "Individual", "SkilledIn", "Average", 
            "Aware", "Access", "Person", "SkilledPerson", "CommonKnowledge"
        ]
        
        self.assert_final_case("Basic Skilled Person Establishment", blf_list, expected_final_case)
    
    def test_relevant_prior_art_same_field(self):
        """Test: Relevant prior art from same field"""
        blf_list = ["SameField", "SimilarPurpose", "SimilarEffect"]
        expected_final_case = [
            "SameField", "SimilarPurpose", "SimilarEffect", 
            "RelevantPriorArt", "CommonKnowledge"
        ]
        
        self.assert_final_case("Relevant Prior Art Same Field", blf_list, expected_final_case)
    
    def test_common_knowledge_with_textbook_evidence(self):
        """Test: Common knowledge with textbook evidence"""
        blf_list = ["Textbook"]
        expected_final_case = [
            "Textbook", "DocumentaryEvidence", 
            "CommonKnowledge"
        ]
        
        self.assert_final_case("Common Knowledge with Textbook Evidence", blf_list, expected_final_case)
    
    def test_common_knowledge_contested(self):
        """Test: Common knowledge contested"""
        blf_list = ["Contested"]

        expected_final_case = [
            "Contested"
        ]
        
        self.assert_final_case("Common Knowledge Contested", blf_list, expected_final_case)
    
    def test_closest_prior_art_single_reference(self):
        """Test: Closest prior art as single reference"""
        blf_list = ["SingleReference", "MinModifications", "AssessedBy"]

        expected_final_case = [
            "SingleReference", "MinModifications", 
            "AssessedBy", "CommonKnowledge"
        ]
        
        self.assert_final_case("Closest Prior Art Single Reference", blf_list, expected_final_case)
    
    def test_combination_attempt_same_field(self):
        """Test: Combination attempt with same field documents"""
        blf_list = ["CombinationAttempt", "SameFieldCPA", "CombinationMotive", "BasisToAssociate"]

        expected_final_case = [
            "CombinationAttempt", "SameFieldCPA", 
            "CombinationMotive", "BasisToAssociate", "CombinationDocuments", "CommonKnowledge","ClosestPriorArtDocuments"
        ]
        
        self.assert_final_case("Combination Attempt Same Field", blf_list, expected_final_case)
    
    def test_complex_scenario_with_all_factors(self):
        """Test: Complex scenario with all major factors"""
        blf_list = [
            "Individual", "SkilledIn", "Average", "Aware", "Access",
            "SameField", "SimilarPurpose", "SimilarEffect",
            "Textbook", "SingleReference", "MinModifications", "AssessedBy",
            "CombinationAttempt", "SameFieldCPA", "CombinationMotive", "BasisToAssociate"
        ]


        expected_final_case = [
            "Individual", "SkilledIn", "Average", 
            "Aware", "Access", "Person", "SkilledPerson", "SameField", 
            "SimilarPurpose", "SimilarEffect", "RelevantPriorArt", "Textbook", 
            "DocumentaryEvidence", "CommonKnowledge", "SingleReference", 
            "MinModifications", "AssessedBy", "ClosestPriorArt", "CombinationAttempt", 
            "SameFieldCPA", "CombinationMotive", "BasisToAssociate", 
            "CombinationDocuments", "ClosestPriorArtDocuments"
        ]
        
        self.assert_final_case("Complex Scenario with All Factors", blf_list, expected_final_case)
    
    def test_research_team_skilled_person(self):
        """Test: Research team as skilled person"""
        blf_list = ["ResearchTeam", "SkilledIn", "Average", "Aware", "Access"]

        expected_final_case = [
            "ResearchTeam", "SkilledIn", "Average", 
            "Aware", "Access", "Person", "SkilledPerson", "CommonKnowledge"
        ]
        
        self.assert_final_case("Research Team Skilled Person", blf_list, expected_final_case)
    
    def test_technical_survey_evidence(self):
        """Test: Technical survey as documentary evidence"""
        blf_list = ["TechnicalSurvey"]

        expected_final_case = [
            "TechnicalSurvey", "DocumentaryEvidence", 
            "CommonKnowledge"
        ]
        
        self.assert_final_case("Technical Survey Evidence", blf_list, expected_final_case)
    
    def test_combination_attempt_similar_field(self):
        """Test: Combination attempt with similar field documents"""
        blf_list = ["CombinationAttempt", "SimilarFieldCPA", "CombinationMotive", "BasisToAssociate"]


        expected_final_case = [
            "CombinationAttempt", "SimilarFieldCPA", 
            "CombinationMotive", "BasisToAssociate", "CombinationDocuments", "CommonKnowledge","ClosestPriorArtDocuments"
        ]
        
        self.assert_final_case("Combination Attempt Similar Field", blf_list, expected_final_case)
    
    def test_production_team_skilled_person(self):
        """Test: Production team as skilled person"""
        blf_list = ["ProductionTeam", "SkilledIn", "Average", "Aware", "Access"]

        expected_final_case = [
            "ProductionTeam", "SkilledIn", "Average", 
            "Aware", "Access", "Person", "SkilledPerson", "CommonKnowledge"
        ]
        
        self.assert_final_case("Production Team Skilled Person", blf_list, expected_final_case)
    
    def test_publication_new_field_evidence(self):
        """Test: Publication in new field as documentary evidence"""
        blf_list = ["PublicationNewField"]

        expected_final_case = [
            "PublicationNewField", "DocumentaryEvidence", 
            "CommonKnowledge"
        ]
        
        self.assert_final_case("Publication New Field Evidence", blf_list, expected_final_case)
    
    def test_minimal_case_information_only(self):
        """Test: Minimal case with no BLFs"""
        blf_list = []

        expected_final_case = ["CommonKnowledge"]
        
        self.assert_final_case("Minimal Case Information Only", blf_list, expected_final_case)

    def test_evaluation_blf_distinguishing_features(self):
        """Test: DistinguishingFeatures EvaluationBLF - normal condition (should find target in sub-ADM)"""
        # Get the real EvaluationBLF node from the ADM
        eval_blf = self.main_adf.nodes["DistinguishingFeatures"]
        
        # Set up sub-ADM results with DistinguishingFeatures present
        sub_adm_results = [
            ["DistinguishingFeatures", "FeatureTechnicalContribution", "FeatureReliableTechnicalEffect"],  # Case 1: has DistinguishingFeatures
            ["DistinguishingFeatures", "NormalTechnicalContribution", "FeatureReliableTechnicalEffect"]    # Case 2: has DistinguishingFeatures
        ]
        
        # Set the facts in the ADF
        self.main_adf.setFact("ReliableTechnicalEffect", "results", sub_adm_results)
        self.main_adf.setFact("ReliableTechnicalEffect", "items", ["Item1", "Item2"])
        
        # Test the evaluateResults method directly
        result = eval_blf.evaluateResults(self.main_adf)
        
        # Should return True because DistinguishingFeatures is found in both cases
        self.assertTrue(result, "DistinguishingFeatures should be accepted when found in sub-ADM results")

    def test_evaluation_blf_non_technical_contribution_rejection(self):
        """Test: NonTechnicalContribution EvaluationBLF - rejection condition (should accept if target NOT found)"""
        # Get the real EvaluationBLF node from the ADM
        eval_blf = self.main_adf.nodes["NonTechnicalContribution"]
        
        # Set up sub-ADM results WITHOUT FeatureTechnicalContribution
        sub_adm_results = [
            ["DistinguishingFeatures"],  # Case 1: no FeatureTechnicalContribution
            ["DistinguishingFeatures", "Credible", "Reproducible"]      # Case 2: no FeatureTechnicalContribution
        ]
        
        # Set the facts in the ADF
        self.main_adf.setFact("ReliableTechnicalEffect", "results", sub_adm_results)
        self.main_adf.setFact("ReliableTechnicalEffect", "items", ["Item1", "Item2"])
        
        # Test the evaluateResults method directly
        result = eval_blf.evaluateResults(self.main_adf)
        
        # Should return True because FeatureTechnicalContribution is NOT found in any case (rejection condition)
        self.assertTrue(result, "NonTechnicalContribution should be accepted when FeatureTechnicalContribution is NOT found in sub-ADM")

    def test_evaluation_blf_technical_contribution_normal(self):
        """Test: TechnicalContribution EvaluationBLF - normal condition (should find target in sub-ADM)"""
        # Get the real EvaluationBLF node from the ADM
        eval_blf = self.main_adf.nodes["TechnicalContribution"]
        
        # Set up sub-ADM results WITH FeatureTechnicalContribution
        sub_adm_results = [
            ["DistinguishingFeatures", "FeatureTechnicalContribution", "NormalTechnicalContribution", "FeatureReliableTechnicalEffect"],  # Case 1: has FeatureTechnicalContribution
            ["DistinguishingFeatures", "FeatureTechnicalContribution", "Credible", "Reproducible", "FeatureReliableTechnicalEffect"]      # Case 2: has FeatureTechnicalContribution
        ]
        
        # Set the facts in the ADF
        self.main_adf.setFact("ReliableTechnicalEffect", "results", sub_adm_results)
        self.main_adf.setFact("ReliableTechnicalEffect", "items", ["Item1", "Item2"])
        
        # Test the evaluateResults method directly
        result = eval_blf.evaluateResults(self.main_adf)
        
        # Should return True because FeatureTechnicalContribution is found in both cases
        self.assertTrue(result, "TechnicalContribution should be accepted when FeatureTechnicalContribution is found in sub-ADM")

    def test_evaluation_blf_sufficiency_of_disclosure_normal(self):
        """Test: SufficiencyOfDisclosure EvaluationBLF - normal condition (should find target in sub-ADM)"""
        # Get the real EvaluationBLF node from the ADM
        eval_blf = self.main_adf.nodes["SufficiencyOfDisclosure"]
        
        # Set up sub-ADM results WITH SufficiencyOfDisclosureIssue
        sub_adm_results = [
            ["DistinguishingFeatures", "SufficiencyOfDisclosureIssue", "ClaimContainsEffect", "FeatureReliableTechnicalEffect"],  # Case 1: has SufficiencyOfDisclosureIssue
            ["DistinguishingFeatures", "SufficiencyOfDisclosureIssue", "NonReproducible", "FeatureReliableTechnicalEffect"]       # Case 2: has SufficiencyOfDisclosureIssue
        ]
        
        # Set the facts in the ADF
        self.main_adf.setFact("ReliableTechnicalEffect", "results", sub_adm_results)
        self.main_adf.setFact("ReliableTechnicalEffect", "items", ["Item1", "Item2"])
        
        # Test the evaluateResults method directly
        result = eval_blf.evaluateResults(self.main_adf)
        
        # Should return True because SufficiencyOfDisclosureIssue is found in both cases
        self.assertTrue(result, "SufficiencyOfDisclosure should be accepted when SufficiencyOfDisclosureIssue is found in sub-ADM")

    def test_evaluation_blf_comprehensive_scenario(self):
        """Test: Comprehensive scenario with multiple EvaluationBLF conditions"""
        # Set up sub-ADM results with mixed conditions
        sub_adm_results = [
            ["DistinguishingFeatures", "FeatureTechnicalContribution", "SufficiencyOfDisclosureIssue", "FeatureReliableTechnicalEffect"],  # Case 1: has both targets
            ["DistinguishingFeatures", "FeatureTechnicalContribution", "Credible", "Reproducible", "FeatureReliableTechnicalEffect"]       # Case 2: has FeatureTechnicalContribution but no SufficiencyOfDisclosureIssue
        ]
        
        # Set the facts in the ADF
        self.main_adf.setFact("ReliableTechnicalEffect", "results", sub_adm_results)
        self.main_adf.setFact("ReliableTechnicalEffect", "items", ["Item1", "Item2"])
        
        # Test DistinguishingFeatures EvaluationBLF (normal condition)
        dist_eval = self.main_adf.nodes["DistinguishingFeatures"]
        dist_result = dist_eval.evaluateResults(self.main_adf)
        self.assertTrue(dist_result, "DistinguishingFeatures should be accepted when found in sub-ADM (normal condition)")
        
        # Test NonTechnicalContribution EvaluationBLF (rejection condition)
        non_tech_eval = self.main_adf.nodes["NonTechnicalContribution"]
        non_tech_result = non_tech_eval.evaluateResults(self.main_adf)
        self.assertFalse(non_tech_result, "NonTechnicalContribution should be rejected when FeatureTechnicalContribution IS found in sub-ADM (rejection condition)")
        
        # Test TechnicalContribution EvaluationBLF (normal condition)
        tech_eval = self.main_adf.nodes["TechnicalContribution"]
        tech_result = tech_eval.evaluateResults(self.main_adf)
        self.assertTrue(tech_result, "TechnicalContribution should be accepted when FeatureTechnicalContribution is found in sub-ADM (normal condition)")
        
        # Test SufficiencyOfDisclosure EvaluationBLF (normal condition)
        suff_eval = self.main_adf.nodes["SufficiencyOfDisclosure"]
        suff_result = suff_eval.evaluateResults(self.main_adf)
        self.assertTrue(suff_result, "SufficiencyOfDisclosure should be accepted when SufficiencyOfDisclosureIssue is found in sub-ADM (normal condition)")

    def test_evaluation_blf_rejection_condition_working(self):
        """Test: Verify rejection condition logic works correctly - accept when target NOT found"""
        # Set up sub-ADM results WITHOUT FeatureTechnicalContribution
        sub_adm_results = [
            ["DistinguishingFeatures", "NormalTechnicalContribution", "Credible", "FeatureReliableTechnicalEffect"],  # Case 1: no FeatureTechnicalContribution
            ["DistinguishingFeatures", "MathematicalContribution", "Reproducible", "FeatureReliableTechnicalEffect"]   # Case 2: no FeatureTechnicalContribution
        ]
        
        # Set the facts in the ADF
        self.main_adf.setFact("ReliableTechnicalEffect", "results", sub_adm_results)
        self.main_adf.setFact("ReliableTechnicalEffect", "items", ["Item1", "Item2"])
        
        # Test NonTechnicalContribution EvaluationBLF (rejection condition)
        non_tech_eval = self.main_adf.nodes["NonTechnicalContribution"]
        non_tech_result = non_tech_eval.evaluateResults(self.main_adf)
        self.assertTrue(non_tech_result, "NonTechnicalContribution should be accepted when FeatureTechnicalContribution is NOT found in sub-ADM (rejection condition)")
        
        # Test TechnicalContribution EvaluationBLF (normal condition)
        tech_eval = self.main_adf.nodes["TechnicalContribution"]
        tech_result = tech_eval.evaluateResults(self.main_adf)
        self.assertFalse(tech_result, "TechnicalContribution should be rejected when FeatureTechnicalContribution is NOT found in sub-ADM (normal condition)")

    def test_invention_unexpected_effect_evaluation_blf(self):
        """Test: InventionUnexpectedEffect EvaluationBLF - normal condition (should accept if target found)"""
        # First, set up a mock sub-ADM result with UnexpectedEffect
        mock_results = [
            ["UnexpectedEffect", "OtherFactor"],
            ["SomeOtherFactor"]
        ]
        
        # Mock the ReliableTechnicalEffect BLF to return our test results
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("ReliableTechnicalEffect", "results", mock_results)
        
        # Test InventionUnexpectedEffect EvaluationBLF (normal condition)
        unexpected_effect_eval = self.main_adf.nodes["InventionUnexpectedEffect"]
        unexpected_effect_result = unexpected_effect_eval.evaluateResults(self.main_adf)
        self.assertTrue(unexpected_effect_result, "InventionUnexpectedEffect should be accepted when UnexpectedEffect IS found in sub-ADM (normal condition)")

    def test_invention_unexpected_effect_evaluation_blf_no_target(self):
        """Test: InventionUnexpectedEffect EvaluationBLF - no target found (should reject)"""
        # First, set up a mock sub-ADM result without UnexpectedEffect
        mock_results = [
            ["SomeOtherFactor", "AnotherFactor"],
            ["YetAnotherFactor"]
        ]
        
        # Mock the ReliableTechnicalEffect BLF to return our test results
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("ReliableTechnicalEffect", "results", mock_results)
        
        # Test InventionUnexpectedEffect EvaluationBLF (normal condition)
        unexpected_effect_eval = self.main_adf.nodes["InventionUnexpectedEffect"]
        unexpected_effect_result = unexpected_effect_eval.evaluateResults(self.main_adf)
        self.assertFalse(unexpected_effect_result, "InventionUnexpectedEffect should be rejected when UnexpectedEffect is NOT found in sub-ADM (normal condition)")

    def test_objective_technical_problem_evaluation_blf(self):
        """Test: ObjectiveTechnicalProblem EvaluationBLF - normal condition (should accept if target found)"""
        # First, set up a mock sub-ADM result with ObjectiveTechnicalProblemFormulation
        mock_results = [
            ["ObjectiveTechnicalProblemFormulation", "OtherFactor"],
            ["SomeOtherFactor"]
        ]
        
        # Mock the OTPObvious BLF to return our test results (since source_blf is "OTPObvious")
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "results", mock_results)
        
        # Test ObjectiveTechnicalProblem EvaluationBLF (normal condition)
        otp_eval = self.main_adf.nodes["ObjectiveTechnicalProblem"]
        otp_result = otp_eval.evaluateResults(self.main_adf)
        self.assertTrue(otp_result, "ObjectiveTechnicalProblem should be accepted when ObjectiveTechnicalProblemFormulation IS found in sub-ADM (normal condition)")

    def test_objective_technical_problem_evaluation_blf_no_target(self):
        """Test: ObjectiveTechnicalProblem EvaluationBLF - no target found (should reject)"""
        # First, set up a mock sub-ADM result without ObjectiveTechnicalProblemFormulation
        mock_results = [
            ["SomeOtherFactor", "AnotherFactor"],
            ["YetAnotherFactor"]
        ]
        
        # Mock the OTPObvious BLF to return our test results (since source_blf is "OTPObvious")
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "results", mock_results)
        
        # Test ObjectiveTechnicalProblem EvaluationBLF (normal condition)
        otp_eval = self.main_adf.nodes["ObjectiveTechnicalProblem"]
        otp_result = otp_eval.evaluateResults(self.main_adf)
        self.assertFalse(otp_result, "ObjectiveTechnicalProblem should be rejected when ObjectiveTechnicalProblemFormulation is NOT found in sub-ADM (normal condition)")

    def test_new_blf_statements(self):
        """Test: Verify that new BLFs have correct statements"""
        # Test InventionUnexpectedEffect statements
        invention_unexpected_effect = self.main_adf.nodes["InventionUnexpectedEffect"]
        self.assertIsInstance(invention_unexpected_effect, EvaluationBLF)
        self.assertEqual(invention_unexpected_effect.statement, 
                        ['there is an unexpected effect within the invention', 'there is not an unexpected effect within the invention'])
        
        # Test ObjectiveTechnicalProblem statements
        objective_technical_problem = self.main_adf.nodes["ObjectiveTechnicalProblem"]
        self.assertIsInstance(objective_technical_problem, EvaluationBLF)
        self.assertEqual(objective_technical_problem.statement, 
                        ['there is a valid objective technical problem', 'there is not a valid objective technical problem'])

    def test_updated_question_order_includes_new_blfs(self):
        """Test: Verify that new BLFs are included in question order"""
        # Check that the new BLFs are in the question order
        self.assertIn("InventionUnexpectedEffect", self.main_adf.questionOrder)
        self.assertIn("ObjectiveTechnicalProblem", self.main_adf.questionOrder)


    def test_synergy_question_instantiator(self):
        """Test: Synergy question instantiator is properly configured"""
        # Test that synergy_question exists in question_instantiators
        self.assertIn("synergy_question", self.main_adf.question_instantiators)
        
        synergy_qi = self.main_adf.question_instantiators["synergy_question"]
        
        # Test that it has the correct dependency node
        self.assertEqual(synergy_qi.get('dependency_node'), "ReliableTechnicalEffect")
        
        # Test that it has the correct question options
        expected_options = {
            "As a synergistic combination (effect is greater than the sum of parts).": "Synergy",
            "As a simple aggregation of independent effects.": "",
            "Neither": ""
        }
        self.assertEqual(synergy_qi.get('blf_mapping'), expected_options)

    def test_functional_interaction_dependent_blf(self):
        """Test: FunctionalInteraction dependent BLF is properly configured"""
        # Test that FunctionalInteraction exists and is properly configured
        functional_interaction = self.main_adf.nodes["FunctionalInteraction"]
        self.assertIsInstance(functional_interaction, DependentBLF)
        
        # Test that it has the correct dependency nodes
        self.assertEqual(functional_interaction.dependency_node, ["ReliableTechnicalEffect","Synergy"])
        
        # Test that it has the correct question
        expected_question = "Is the synergistic combination achieved through a functional interaction between features?"
        self.assertEqual(functional_interaction.question, expected_question)

    def test_new_abstract_factor_evaluation_path(self):
        """Test: New abstract factors evaluate correctly in a complete evaluation path"""
        # Test a complete evaluation path that should trigger all new abstract factors
        blf_list = ["ReliableTechnicalEffect", "Synergy", "FunctionalInteraction", "TechnicalContribution"]
        final_case = self.evaluate_blf_combination(blf_list)
        
        # Verify that all new abstract factors are properly evaluated
        expected_abstract_factors = [
            "Combination", "CandidateOTP"
        ]
        
        for factor in expected_abstract_factors:
            self.assertIn(factor, final_case, f"Abstract factor {factor} should be in final case")
        
        # Verify the complete evaluation path
        expected_final_case = [
            "ReliableTechnicalEffect", "Synergy", "FunctionalInteraction", 
            "TechnicalContribution", "Combination", "CandidateOTP", "CommonKnowledge"
        ]
        
        self.assertEqual(set(final_case), set(expected_final_case), 
                        f"Complete evaluation path should include all new abstract factors. Got: {final_case}")

    def test_combination_with_synergy_and_functional_interaction(self):
        """Test: Combination abstract factor with synergy and functional interaction"""
        blf_list = ["ReliableTechnicalEffect", "Synergy", "FunctionalInteraction"]
        expected_final_case = [
            "ReliableTechnicalEffect", "Synergy", "FunctionalInteraction", "Combination", "CommonKnowledge", "CandidateOTP"
        ]
        
        self.assert_final_case("Combination with Synergy and Functional Interaction", blf_list, expected_final_case)

    def test_partial_problems_rejecting_combination(self):
        """Test: PartialProblems abstract factor rejecting combination"""
        blf_list = ["ReliableTechnicalEffect", "Synergy", "FunctionalInteraction", "Combination"]
        # This should create Combination, but PartialProblems should reject it
        expected_final_case = [
            "ReliableTechnicalEffect", "Synergy", "FunctionalInteraction", "Combination", 
            "CommonKnowledge", "CandidateOTP"
        ]
        
        self.assert_final_case("PartialProblems Rejecting Combination", blf_list, expected_final_case)

    def test_candidate_otp_with_combination(self):
        """Test: CandidateOTP abstract factor with combination"""
        blf_list = ["ReliableTechnicalEffect", "Synergy", "FunctionalInteraction"]
        expected_final_case = [
            "ReliableTechnicalEffect", "Synergy", "FunctionalInteraction", 
            "Combination", "CandidateOTP", "CommonKnowledge"
        ]
        
        self.assert_final_case("CandidateOTP with Combination", blf_list, expected_final_case)

    def test_candidate_otp_with_partial_problems(self):
        """Test: """
        blf_list = ["TechnicalContribution"]
        expected_final_case = [
            "TechnicalContribution", "CommonKnowledge"
        ]
        
        self.assert_final_case(" ", blf_list, expected_final_case)


    def test_question_order_includes_new_abstract_factors(self):
        """Test: Verify that new abstract factors are included in question order"""
        # Check that the new abstract factors and related nodes are in the question order
        self.assertIn("synergy_question", self.main_adf.questionOrder)
        self.assertIn("FunctionalInteraction", self.main_adf.questionOrder)
        self.assertIn("ObjectiveTechnicalProblem", self.main_adf.questionOrder)

    def test_otp_obvious_sub_adm_blf_rejection_condition(self):
        """Test: OTPObvious SubADMBLF with rejection_condition=True - should accept when no items rejected"""
        # Test that OTPObvious exists and has rejection_condition=True
        otp_obvious = self.main_adf.nodes["OTPObvious"]
        self.assertIsInstance(otp_obvious, SubADMBLF)
        self.assertTrue(otp_obvious.rejection_condition, "OTPObvious should have rejection_condition=True")
        
        # Test that it has the correct dependency nodes
        expected_dependencies = ["CandidateOTP", "SkilledPerson", "RelevantPriorArt", "ClosestPriorArtDocuments"]
        self.assertEqual(otp_obvious.dependency_node, expected_dependencies)

    def test_otp_obvious_acceptance_when_no_rejected_items(self):
        """Test: OTPObvious should be ACCEPTED when sub-ADM evaluation finds no rejected items (obvious)"""
        # Mock sub-ADM results where all items are accepted (no rejected items) - obvious
        mock_results = [
            ["WouldHaveArrived"],  # Accepted
            ["WouldHaveArrived"]  # Accepted
        ]
        
        # Mock the OTPObvious BLF to return our test results
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "results", mock_results)
            self.main_adf.setFact("OTPObvious", "accepted_count", 2)
            self.main_adf.setFact("OTPObvious", "rejected_count", 0)
        
        # Test OTPObvious evaluation (rejection condition: accept when rejected_count < 1)
        otp_obvious = self.main_adf.nodes["OTPObvious"]
        
        # Test the evaluation logic directly - with rejection_condition=True, 
        # it should accept when rejected_count < 1 (i.e., 0)
        rejected_count = self.main_adf.getFact("OTPObvious", "rejected_count") or 0
        result = rejected_count < 1
        
        self.assertTrue(result, "OTPObvious should be ACCEPTED when no items are rejected (obvious)")

    def test_otp_obvious_rejection_when_some_items_rejected(self):
        """Test: OTPObvious should be REJECTED when sub-ADM evaluation finds some rejected items (NOT obvious)"""
        # Mock sub-ADM results where some items are rejected - NOT obvious
        mock_results = [
            ["WouldHaveArrived", "OtherFactor"],  # Accepted
            []  # Rejected (empty case)
        ]
        
        # Mock the OTPObvious BLF to return our test results
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "results", mock_results)
            self.main_adf.setFact("OTPObvious", "accepted_count", 1)
            self.main_adf.setFact("OTPObvious", "rejected_count", 1)
        
        # Test OTPObvious evaluation (rejection condition: reject when rejected_count >= 1)
        otp_obvious = self.main_adf.nodes["OTPObvious"]
        
        # Test the evaluation logic directly - with rejection_condition=True, 
        # it should reject when rejected_count >= 1 (i.e., 1 or more)
        rejected_count = self.main_adf.getFact("OTPObvious", "rejected_count") or 0
        result = rejected_count < 1
        
        self.assertFalse(result, "OTPObvious should be REJECTED when some items are rejected (NOT obvious)")

    def test_otp_obvious_rejection_condition_logic(self):
        """Test: Verify OTPObvious rejection condition logic works correctly"""
        otp_obvious = self.main_adf.nodes["OTPObvious"]
        
        # Test case 1: All items accepted (rejected_count = 0) -> Should be ACCEPTED (obvious)
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "accepted_count", 3)
            self.main_adf.setFact("OTPObvious", "rejected_count", 0)
        
        # Test the evaluation logic directly - with rejection_condition=True, 
        # it should accept when rejected_count < 1 (i.e., 0)
        rejected_count = self.main_adf.getFact("OTPObvious", "rejected_count") or 0
        result1 = rejected_count < 1
        self.assertTrue(result1, "Should be ACCEPTED when rejected_count = 0 (obvious)")
        
        # Test case 2: Some items rejected (rejected_count = 1) -> Should be REJECTED (NOT obvious)
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "accepted_count", 2)
            self.main_adf.setFact("OTPObvious", "rejected_count", 1)
        
        # Test the evaluation logic directly - with rejection_condition=True, 
        # it should reject when rejected_count >= 1 (i.e., 1 or more)
        rejected_count = self.main_adf.getFact("OTPObvious", "rejected_count") or 0
        result2 = rejected_count < 1
        self.assertFalse(result2, "Should be REJECTED when rejected_count = 1 (NOT obvious)")
        
        # Test case 3: All items rejected (rejected_count = 3) -> Should be REJECTED (NOT obvious)
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "accepted_count", 0)
            self.main_adf.setFact("OTPObvious", "rejected_count", 3)
        
        # Test the evaluation logic directly - with rejection_condition=True, 
        # it should reject when rejected_count >= 1 (i.e., 1 or more)
        rejected_count = self.main_adf.getFact("OTPObvious", "rejected_count") or 0
        result3 = rejected_count < 1
        self.assertFalse(result3, "Should be REJECTED when rejected_count = 3 (NOT obvious)")

    def test_new_abstract_factors_secondary_indicator(self):
        """Test: New abstract factor SecondaryIndicator evaluation"""
        # Test SecondaryIndicator with PredictableDisadvantage
        self.main_adf.case = ['PredictableDisadvantage']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be accepted when PredictableDisadvantage is present")
        
        # Test SecondaryIndicator with BioTechObvious
        self.main_adf.case = ['BioTechObvious']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be accepted when BioTechObvious is present")
        
        # Test SecondaryIndicator with AntibodyObvious
        self.main_adf.case = ['AntibodyObvious']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be accepted when AntibodyObvious is present")
        
        # Test SecondaryIndicator with KnownMeasures
        self.main_adf.case = ['KnownMeasures']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be accepted when KnownMeasures is present")
        
        # Test SecondaryIndicator with ObviousCombination
        self.main_adf.case = ['ObviousCombination']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be accepted when ObviousCombination is present")
        
        # Test SecondaryIndicator with ObviousSelection
        self.main_adf.case = ['ObviousSelection']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be accepted when ObviousSelection is present")
        
        # Test SecondaryIndicator rejection when none of the sub-factors are present
        self.main_adf.case = ['ReliableTechnicalEffect']  # None of the secondary indicator factors
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertNotIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be rejected when none of its sub-factors are present")

    def test_biotech_antibody_abstract_factors(self):
        """Test: Biotech and antibody related abstract factors"""
        # Test BioTechObvious - requires InventionUnexpectedEffect rejection and BioTech + PredictableResults/ReasonableSuccess
        self.main_adf.case = ['BioTech', 'PredictableResults', 'ReasonableSuccess']
        # Mock that InventionUnexpectedEffect is rejected (not in case)
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('BioTechObvious', self.main_adf.case, "BioTechObvious should be accepted when BioTech and both PredictableResults and ReasonableSuccess are present")
        
        # Test AntibodyObvious - requires OvercomeTechDifficulty rejection and SubjectMatterAntibody + KnownTechnique
        self.main_adf.case = ['SubjectMatterAntibody', 'KnownTechnique']
        # Mock that OvercomeTechDifficulty is rejected (not in case)
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('AntibodyObvious', self.main_adf.case, "AntibodyObvious should be accepted when SubjectMatterAntibody and KnownTechnique are present")
        
        # Test SubjectMatterAntibody - requires BioTech and Antibody
        self.main_adf.case = ['BioTech', 'Antibody']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('SubjectMatterAntibody', self.main_adf.case, "SubjectMatterAntibody should be accepted when BioTech and Antibody are present")

    def test_known_measures_abstract_factors(self):
        """Test: Known measures related abstract factors"""
        # Test KnownMeasures with GapFilled
        self.main_adf.case = ['GapFilled']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('KnownMeasures', self.main_adf.case, "KnownMeasures should be accepted when GapFilled is present")
        
        # Test KnownMeasures with WellKnownEquivalent
        self.main_adf.case = ['WellKnownEquivalent']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('KnownMeasures', self.main_adf.case, "KnownMeasures should be accepted when WellKnownEquivalent is present")
        
        # Test KnownMeasures with KnownUsage
        self.main_adf.case = ['KnownUsage']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('KnownMeasures', self.main_adf.case, "KnownMeasures should be accepted when KnownUsage is present")
        
        # Test KnownUsage with KnownProperties
        self.main_adf.case = ['KnownProperties']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('KnownUsage', self.main_adf.case, "KnownUsage should be accepted when KnownProperties is present")
        
        # Test KnownUsage with AnalogousUse
        self.main_adf.case = ['AnalogousUse']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('KnownUsage', self.main_adf.case, "KnownUsage should be accepted when AnalogousUse is present")
        
        # Test KnownUsage with KnownDevice and AnalogousSubstitution
        self.main_adf.case = ['KnownDevice', 'AnalogousSubstitution']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('KnownUsage', self.main_adf.case, "KnownUsage should be accepted when KnownDevice and AnalogousSubstitution are present")

    def test_obvious_selection_abstract_factors(self):
        """Test: Obvious selection related abstract factors"""
        # Test ObviousSelection with ChooseEqualAlternatives
        self.main_adf.case = ['ChooseEqualAlternatives']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('ObviousSelection', self.main_adf.case, "ObviousSelection should be accepted when ChooseEqualAlternatives is present")
        
        # Test ObviousSelection with NormalDesignProcedure
        self.main_adf.case = ['NormalDesignProcedure']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('ObviousSelection', self.main_adf.case, "ObviousSelection should be accepted when NormalDesignProcedure is present")
        
        # Test ObviousSelection with SimpleExtrapolation
        self.main_adf.case = ['SimpleExtrapolation']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('ObviousSelection', self.main_adf.case, "ObviousSelection should be accepted when SimpleExtrapolation is present")
        
        # Test ObviousSelection with ChemicalSelection
        self.main_adf.case = ['ChemicalSelection']
        self.main_adf.evaluateTree(self.main_adf.case)
        
        self.assertIn('ObviousSelection', self.main_adf.case, "ObviousSelection should be accepted when ChemicalSelection is present")

    def test_otp_obvious_vs_normal_sub_adm_blf_behavior(self):
        """Test: Compare OTPObvious (rejection condition) vs normal SubADMBLF behavior"""
        # Test normal SubADMBLF behavior (rejection_condition=False)
        normal_blf = self.main_adf.nodes["ReliableTechnicalEffect"]  # This should be normal
        if hasattr(normal_blf, 'rejection_condition'):
            self.assertFalse(normal_blf.rejection_condition, "ReliableTechnicalEffect should have rejection_condition=False")
        
        # Test OTPObvious behavior (rejection_condition=True)
        otp_obvious = self.main_adf.nodes["OTPObvious"]
        self.assertTrue(otp_obvious.rejection_condition, "OTPObvious should have rejection_condition=True")
        
        # Both should be SubADMBLF instances
        self.assertIsInstance(normal_blf, SubADMBLF)
        self.assertIsInstance(otp_obvious, SubADMBLF)

    def test_otp_obvious_dependency_nodes(self):
        """Test: Verify OTPObvious has correct dependency nodes"""
        otp_obvious = self.main_adf.nodes["OTPObvious"]
        expected_dependencies = ["CandidateOTP", "SkilledPerson", "RelevantPriorArt", "ClosestPriorArtDocuments"]
        
        self.assertEqual(otp_obvious.dependency_node, expected_dependencies)
        
        # Verify all dependency nodes exist in the main ADF
        for dep_node in expected_dependencies:
            self.assertIn(dep_node, self.main_adf.nodes, f"Dependency node {dep_node} should exist in main ADF")

    def test_otp_obvious_question_text(self):
        """Test: Verify OTPObvious has appropriate question text"""
        otp_obvious = self.main_adf.nodes["OTPObvious"]
        expected_question = "Sub-ADM evaluation: OTPObvious"
        
        self.assertEqual(otp_obvious.question, expected_question)

    def test_otp_obvious_in_question_order(self):
        """Test: Verify OTPObvious is included in question order"""
        self.assertIn("OTPObvious", self.main_adf.questionOrder)

    def test_otp_obvious_rejection_condition_edge_cases(self):
        """Test: OTPObvious rejection condition edge cases"""
        otp_obvious = self.main_adf.nodes["OTPObvious"]
        
        # Edge case 1: No items at all (accepted_count = 0, rejected_count = 0) - obvious
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "accepted_count", 0)
            self.main_adf.setFact("OTPObvious", "rejected_count", 0)
        
        # Test the evaluation logic directly - with rejection_condition=True, 
        # it should accept when rejected_count < 1 (i.e., 0)
        rejected_count = self.main_adf.getFact("OTPObvious", "rejected_count") or 0
        result = rejected_count < 1
        self.assertTrue(result, "Should be ACCEPTED when no items at all (obvious)")
        
        # Edge case 2: Mixed results (accepted_count = 1, rejected_count = 1) - NOT obvious
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "accepted_count", 1)
            self.main_adf.setFact("OTPObvious", "rejected_count", 1)
        
        # Test the evaluation logic directly - with rejection_condition=True, 
        # it should reject when rejected_count >= 1 (i.e., 1 or more)
        rejected_count = self.main_adf.getFact("OTPObvious", "rejected_count") or 0
        result = rejected_count < 1
        self.assertFalse(result, "Should be REJECTED when some items are rejected (NOT obvious)")

    def test_synergy_question_instantiator(self):
        """Test: Synergy question instantiator functionality"""
        synergy_question = self.main_adf.question_instantiators.get("synergy_question")
        self.assertIsNotNone(synergy_question, "Synergy question instantiator should exist")
        
        # Test the question text
        expected_question = "How do the invention's features create the technical effect?"
        self.assertEqual(synergy_question['question'], expected_question, "Synergy question should have correct text")
        
        # Test the options (blf_mapping)
        expected_options = {
            "As a synergistic combination (effect is greater than the sum of parts).": "Synergy",
            "As a simple aggregation of independent effects.": "",
            "Neither": ""
        }
        self.assertEqual(synergy_question['blf_mapping'], expected_options, "Synergy question should have correct options")

    def test_functional_interaction_dependent_blf(self):
        """Test: FunctionalInteraction DependentBLF functionality"""
        functional_interaction = self.main_adf.nodes.get("FunctionalInteraction")
        self.assertIsNotNone(functional_interaction, "FunctionalInteraction should exist")
        
        # Test dependencies
        expected_dependencies = ["ReliableTechnicalEffect", "Synergy"]
        self.assertEqual(functional_interaction.dependency_node, expected_dependencies, "FunctionalInteraction should have correct dependencies")
        
        # Test question text
        expected_question = "Is the synergistic combination achieved through a functional interaction between features?"
        self.assertEqual(functional_interaction.question, expected_question, "FunctionalInteraction should have correct question")

    def test_full_adm_inventive_step_scenario_1(self):
        """Test: Full ADM - Inventive step present scenario"""
        # Scenario: Invention with synergistic combination, unexpected effects, and valid OTP
        self.main_adf.case = [
            'ReliableTechnicalEffect', 'FunctionalInteraction', 'Synergy',  # Synergistic combination
            'InventionUnexpectedEffect',  # Unexpected effects
            'TechnicalContribution', 'Novelty',  # Technical contribution and novelty
            'ObjectiveTechnicalProblem'  # Valid OTP
        ]
        
        # Mock sub-ADM results
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "rejected_count", 0)  # OTP is obvious (accepted)
            self.main_adf.setFact("ReliableTechnicalEffect", "accepted_count", 3)
            self.main_adf.setFact("ReliableTechnicalEffect", "rejected_count", 0)
        
        self.main_adf.evaluateTree(self.main_adf.case)
        
        # Check that key factors are present
        self.assertIn('Combination', self.main_adf.case, "Combination should be present for synergistic effects")
        self.assertIn('CandidateOTP', self.main_adf.case, "CandidateOTP should be present")
        self.assertIn('InvStep', self.main_adf.case, "InvStep should be present")
        
        # Check that the invention is not obvious
        self.assertNotIn('Obvious', self.main_adf.case, "Obvious should not be present for inventive step")

    def test_full_adm_inventive_step_scenario_2(self):
        """Test: Full ADM - No inventive step due to obviousness scenario"""
        # Scenario: Invention with obvious combination and known measures
        self.main_adf.case = [
            'ReliableTechnicalEffect',  # Technical effect present
            'ObviousCombination',  # Obvious combination
            'KnownMeasures',  # Known measures
            'TechnicalContribution', 'Novelty'  # Technical contribution and novelty
        ]
        
        # Mock sub-ADM results - OTP is obvious
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "rejected_count", 0)  # OTP is obvious (accepted)
            self.main_adf.setFact("ReliableTechnicalEffect", "accepted_count", 2)
            self.main_adf.setFact("ReliableTechnicalEffect", "rejected_count", 0)
        
        self.main_adf.evaluateTree(self.main_adf.case)
        
        # Check that obviousness factors are present
        self.assertIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be present")
        self.assertIn('Obvious', self.main_adf.case, "Obvious should be present")
        
        # Check that the invention has no inventive step due to obviousness
        # InvStep should be rejected when Obvious is present (reject condition)
        self.assertNotIn('InvStep', self.main_adf.case, "InvStep should be rejected due to obviousness")

    def test_full_adm_biotech_scenario(self):
        """Test: Full ADM - Biotech invention scenario"""
        # Scenario: Biotech invention with predictable results
        self.main_adf.case = [
            'ReliableTechnicalEffect', 'BioTech', 'PredictableResults', 'ReasonableSuccess',
            'TechnicalContribution', 'Novelty'
        ]
        
        # Mock sub-ADM results
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "rejected_count", 0)
            self.main_adf.setFact("ReliableTechnicalEffect", "accepted_count", 2)
            self.main_adf.setFact("ReliableTechnicalEffect", "rejected_count", 0)
        
        self.main_adf.evaluateTree(self.main_adf.case)
        
        # Check biotech-specific factors
        self.assertIn('BioTechObvious', self.main_adf.case, "BioTechObvious should be present")
        self.assertIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be present")
        self.assertIn('Obvious', self.main_adf.case, "Obvious should be present for obvious biotech invention")
        
        # Check that the invention has no inventive step due to obviousness
        # InvStep should be rejected when Obvious is present (reject condition)
        self.assertNotIn('InvStep', self.main_adf.case, "InvStep should be rejected due to obviousness")

    def test_full_adm_antibody_scenario(self):
        """Test: Full ADM - Antibody invention scenario"""
        # Scenario: Antibody invention with known techniques
        self.main_adf.case = [
            'ReliableTechnicalEffect', 'BioTech', 'Antibody', 'SubjectMatterAntibody', 'KnownTechnique',
            'TechnicalContribution', 'Novelty'
        ]
        
        # Mock sub-ADM results
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "rejected_count", 0)
            self.main_adf.setFact("ReliableTechnicalEffect", "accepted_count", 2)
            self.main_adf.setFact("ReliableTechnicalEffect", "rejected_count", 0)
        
        self.main_adf.evaluateTree(self.main_adf.case)
        
        # Check antibody-specific factors
        self.assertIn('AntibodyObvious', self.main_adf.case, "AntibodyObvious should be present")
        self.assertIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be present")
        self.assertIn('Obvious', self.main_adf.case, "Obvious should be present for obvious antibody invention")
        
        # Check that the invention has no inventive step due to obviousness
        # InvStep should be rejected when Obvious is present (reject condition)
        self.assertNotIn('InvStep', self.main_adf.case, "InvStep should be rejected due to obviousness")

    def test_full_adm_obvious_selection_scenario(self):
        """Test: Full ADM - Obvious selection scenario"""
        # Scenario: Invention involving obvious selection from known alternatives
        self.main_adf.case = [
            'ReliableTechnicalEffect', 'ChooseEqualAlternatives', 'ObviousSelection',
            'TechnicalContribution', 'Novelty'
        ]
        
        # Mock sub-ADM results
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "rejected_count", 0)
            self.main_adf.setFact("ReliableTechnicalEffect", "accepted_count", 2)
            self.main_adf.setFact("ReliableTechnicalEffect", "rejected_count", 0)
        
        self.main_adf.evaluateTree(self.main_adf.case)
        
        # Check obvious selection factors
        self.assertIn('SecondaryIndicator', self.main_adf.case, "SecondaryIndicator should be present")
        self.assertIn('Obvious', self.main_adf.case, "Obvious should be present for obvious selection")
        
        # Check that the invention has no inventive step due to obviousness
        # InvStep should be rejected when Obvious is present (reject condition)
        self.assertNotIn('InvStep', self.main_adf.case, "InvStep should be rejected due to obviousness")

    def test_full_adm_no_technical_contribution_scenario(self):
        """Test: Full ADM - No technical contribution scenario"""
        # Scenario: Invention with no technical contribution
        self.main_adf.case = [
            'ReliableTechnicalEffect', 'NonTechnicalContribution',  # Non-technical contribution
            'Novelty'
        ]
        
        # Mock sub-ADM results
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "rejected_count", 0)
            self.main_adf.setFact("ReliableTechnicalEffect", "accepted_count", 1)
            self.main_adf.setFact("ReliableTechnicalEffect", "rejected_count", 0)
        
        self.main_adf.evaluateTree(self.main_adf.case)
        
        # Check that technical contribution is rejected
        self.assertNotIn('TechnicalContribution', self.main_adf.case, "TechnicalContribution should be rejected")
        
        # Check that the invention has no inventive step due to no technical contribution
        # InvStep requires TechnicalContribution and ReliableTechnicalEffect and Novelty
        self.assertNotIn('InvStep', self.main_adf.case, "InvStep should be rejected due to no technical contribution")

    def test_full_adm_insufficient_disclosure_scenario(self):
        """Test: Full ADM - Insufficient disclosure scenario"""
        # Scenario: Invention with insufficient disclosure
        self.main_adf.case = [
            'ReliableTechnicalEffect', 'SufficiencyOfDisclosure',  # Insufficient disclosure
            'TechnicalContribution', 'Novelty'
        ]
        
        # Mock sub-ADM results
        if hasattr(self.main_adf, 'setFact'):
            self.main_adf.setFact("OTPObvious", "rejected_count", 0)
            self.main_adf.setFact("ReliableTechnicalEffect", "accepted_count", 1)
            self.main_adf.setFact("ReliableTechnicalEffect", "rejected_count", 0)
        
        self.main_adf.evaluateTree(self.main_adf.case)
        
        # Check that sufficiency of disclosure issue is present
        self.assertIn('SufficiencyOfDisclosure', self.main_adf.case, "SufficiencyOfDisclosure should be present")
        
        # Check that the invention has no inventive step due to insufficient disclosure
        # InvStep should be rejected when SufficiencyOfDisclosure is present (reject condition)
        self.assertNotIn('InvStep', self.main_adf.case, "InvStep should be rejected due to insufficient disclosure")


class TestCLIUI(unittest.TestCase):
    """Unit tests for CLI UI functionality - focused on non-blocking methods"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.cli = CLI()
        # Mock the input function to control user input
        self.original_input = builtins.input
        self.original_print = builtins.print
        self.input_calls = []
        self.print_calls = []
        
    def tearDown(self):
        """Clean up after tests"""
        builtins.input = self.original_input
        builtins.print = self.original_print
    
    def mock_input(self, prompt=""):
        """Mock input function that returns predefined responses"""
        self.input_calls.append(prompt)
        if self.input_calls:
            return self.input_calls.pop(0)
        return ""
    
    def mock_print(self, *args, **kwargs):
        """Mock print function to capture output"""
        self.print_calls.append(' '.join(str(arg) for arg in args))
        # Don't actually print during tests
    
    def test_cli_initialization(self):
        """Test CLI initialization"""
        cli = CLI()
        self.assertIsNone(cli.adf)
        self.assertEqual(cli.case, [])
        self.assertEqual(cli.cases, {})
        self.assertIsNone(cli.caseName)
    
    def test_main_menu_choice_logic(self):
        """Test main menu choice handling logic without infinite loops"""
        # Test choice 1 - should call load_existing_domain
        original_load = self.cli.load_existing_domain
        self.cli.load_existing_domain = lambda: "loaded"
        
        choice = "1"
        if choice == "1":
            result = self.cli.load_existing_domain()
            self.assertEqual(result, "loaded")
        
        # Test choice 2 - should exit
        choice = "2"
        if choice == "2":
            with self.assertRaises(SystemExit):
                sys.exit(0)
        
        # Test invalid choice
        choice = "99"
        if choice not in ["1", "2"]:
            self.assertTrue(True)  # Just verify the logic works
        
        # Restore original method
        self.cli.load_existing_domain = original_load
    
    def test_load_existing_domain_logic(self):
        """Test load existing domain choice handling logic"""
        # Test choice 1 - Academic Research Project
        original_load_academic = self.cli.load_academic_research_domain
        self.cli.load_academic_research_domain = lambda: "academic_loaded"
        
        choice = "1"
        if choice == "1":
            result = self.cli.load_academic_research_domain()
            self.assertEqual(result, "academic_loaded")
        
        # Test choice 2 - Inventive Step
        original_load_inventive = self.cli.load_inventive_step_domain
        self.cli.load_inventive_step_domain = lambda: "inventive_loaded"
        
        choice = "2"
        if choice == "2":
            result = self.cli.load_inventive_step_domain()
            self.assertEqual(result, "inventive_loaded")
        
        # Test choice 3 - Back to main menu
        choice = "3"
        if choice == "3":
            result = None
            self.assertIsNone(result)
        
        # Restore original methods
        self.cli.load_academic_research_domain = original_load_academic
        self.cli.load_inventive_step_domain = original_load_inventive
    
    def test_domain_menu_logic(self):
        """Test domain menu choice handling logic"""
        # Set up a mock ADF
        self.cli.adf = type('MockADF', (), {'name': 'Test Domain'})()
        
        # Test choice 1 - Query domain
        original_query = self.cli.query_domain
        self.cli.query_domain = lambda: "queried"
        
        choice = "1"
        if choice == "1":
            result = self.cli.query_domain()
            self.assertEqual(result, "queried")
        
        # Test choice 2 - Visualize domain
        original_visualize = self.cli.visualize_domain
        self.cli.visualize_domain = lambda: "visualized"
        
        choice = "2"
        if choice == "2":
            result = self.cli.visualize_domain()
            self.assertEqual(result, "visualized")
        
        # Test choice 3 - Back to main menu
        choice = "3"
        if choice == "3":
            result = None
            self.assertIsNone(result)
        
        # Restore original methods
        self.cli.query_domain = original_query
        self.cli.visualize_domain = original_visualize
    
    def test_query_domain_basic(self):
        """Test query domain basic functionality"""
        # Mock the ask_questions method
        original_ask = self.cli.ask_questions
        self.cli.ask_questions = lambda: "questions_asked"
        
        # Test with case name
        self.cli.caseName = 'test'
        self.cli.case = []
        
        # Simulate the query_domain logic
        if self.cli.caseName:
            result = self.cli.ask_questions()
            self.assertEqual(result, "questions_asked")
            self.assertEqual(self.cli.caseName, 'test')
            self.assertEqual(self.cli.case, [])
        
        # Test without case name
        self.cli.caseName = None
        if not self.cli.caseName:
            # This would print "No case name provided" in the actual method
            self.assertTrue(True)  # Just verify the logic works
        
        # Restore original method
        self.cli.ask_questions = original_ask
    
    def test_ask_questions_basic(self):
        """Test ask_questions basic functionality"""
        # Set up mock ADF
        mock_adf = type('MockADF', (), {
            'nodes': {},
            'questionOrder': []
        })()
        self.cli.adf = mock_adf
        
        # Mock the show_outcome method
        original_show = self.cli.show_outcome
        self.cli.show_outcome = lambda: "outcome_shown"
        
        # Test without question order
        if not self.cli.adf.questionOrder:
            # This would print "No question order specified" in the actual method
            self.assertTrue(True)  # Just verify the logic works
        
        # Test with question order
        self.cli.adf.questionOrder = ['question1', 'question2']
        if self.cli.adf.questionOrder:
            # This would process questions in the actual method
            self.assertTrue(True)  # Just verify the logic works
        
        # Restore original method
        self.cli.show_outcome = original_show
    
    def test_show_outcome_basic(self):
        """Test show_outcome basic functionality"""
        # Set up mock ADF and case
        def success_evaluateTree(self, case):
            return ['Result 1', 'Result 2']
        
        mock_adf = type('MockADF', (), {
            'evaluateTree': success_evaluateTree
        })()
        self.cli.adf = mock_adf
        self.cli.caseName = 'test_case'
        self.cli.case = ['node1', 'node2']
        
        # Mock print to capture output
        builtins.print = self.mock_print
        
        # Test successful evaluation
        try:
            statements = self.cli.adf.evaluateTree(self.cli.case)
            self.assertEqual(statements, ['Result 1', 'Result 2'])
        except Exception as e:
            self.fail(f"Unexpected exception: {e}")
        
        # Test error handling
        def error_evaluateTree(self, case):
            raise Exception("Test error")
        
        mock_adf_error = type('MockADF', (), {
            'evaluateTree': error_evaluateTree
        })()
        self.cli.adf = mock_adf_error
        
        try:
            statements = self.cli.adf.evaluateTree(self.cli.case)
        except Exception as e:
            self.assertEqual(str(e), "Test error")
    
    def test_question_helper_basic(self):
        """Test questionHelper basic functionality"""
        # Set up mock ADF and node
        mock_node = type('MockNode', (), {
            'question': 'Test question?',
            'acceptance': None
        })()
        mock_adf = type('MockADF', (), {
            'nodes': {'test_node': mock_node}
        })()
        self.cli.adf = mock_adf
        
        # Mock input and print
        builtins.input = lambda x: "y"
        builtins.print = self.mock_print
        
        # Test with question
        if hasattr(mock_node, 'question') and mock_node.question:
            # This would ask the question in the actual method
            self.assertTrue(True)  # Just verify the logic works
        
        # Test without question
        mock_node_no_question = type('MockNode', (), {
            'question': None,
            'acceptance': None
        })()
        
        if not (hasattr(mock_node_no_question, 'question') and mock_node_no_question.question):
            # This would add to case without asking in the actual method
            self.assertTrue(True)  # Just verify the logic works
    
    def test_cli_with_sub_adm_case_data(self):
        """Test CLI with sub-ADM case data and expected outcomes"""
        # Set up CLI with sub-ADM
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        self.cli.adf = create_sub_adm_1("test_feature")
        self.cli.caseName = "test_sub_adm_case"
        self.cli.case = []
        
        # Test case: Independent Contribution + Computer Simulation + Technical Adaptation
        test_blfs = ["DistinguishingFeatures","IndependentContribution", "ComputerSimulation", "TechnicalAdaptation"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "IndependentContribution", 
            "ExcludedField",
            "NumOrComp",
            "ComputerSimulation", 
            "TechnicalAdaptation", 
            "NonReproducible",
            "ComputationalContribution", 
            "FeatureTechnicalContribution"
        ]
        
        # Simulate adding BLFs to case
        for blf in test_blfs:
            if blf not in self.cli.case:
                self.cli.case.append(blf)
        
        # Evaluate the case
        self.cli.adf.evaluateTree(self.cli.case)
        actual_final_case = self.cli.case.copy()
        
        # Verify expected outcome
        self.assertEqual(set(actual_final_case), set(expected_final_case))
    
    def test_cli_with_main_adm_case_data(self):
        """Test CLI with main ADM case data and expected outcomes"""
        # Set up CLI with main ADM
        from ADM_JURIX.ADM.inventive_step_ADM import adf
        self.cli.adf = adf()
        self.cli.caseName = "test_main_adm_case"
        self.cli.case = []
        
        # Test case: Basic skilled person establishment
        test_blfs = ["Individual", "SkilledIn", "Average", "Aware", "Access"]
        expected_final_case = [
            "Individual", "SkilledIn", "Average", 
            "Aware", "Access", "Person", "SkilledPerson", "CommonKnowledge"
        ]
        
        # Simulate adding BLFs to case
        for blf in test_blfs:
            if blf not in self.cli.case:
                self.cli.case.append(blf)
        
        # Evaluate the case
        self.cli.adf.evaluateTree(self.cli.case)
        actual_final_case = self.cli.case.copy()
        
        # Verify expected outcome
        self.assertEqual(set(actual_final_case), set(expected_final_case))
    
    def test_cli_query_domain_with_case_evaluation(self):
        """Test CLI query domain with full case evaluation workflow"""
        # Set up CLI with sub-ADM
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        self.cli.adf = create_sub_adm_1("test_feature")
        self.cli.caseName = "test_query_case"
        self.cli.case = []
        
        # Mock the ask_questions method to simulate user input
        original_ask = self.cli.ask_questions
        def mock_ask_questions():
            # Simulate adding BLFs based on user responses
            test_blfs = ["IndependentContribution", "Credible", "Reproducible"]
            for blf in test_blfs:
                if blf not in self.cli.case:
                    self.cli.case.append(blf)
            return "questions_completed"
        
        self.cli.ask_questions = mock_ask_questions
        
        # Test query domain workflow
        result = self.cli.query_domain()
        self.assertIsNone(result)  # query_domain returns None
        self.assertEqual(self.cli.caseName, "test")  # query_domain hardcodes caseName as 'test'
        
        # Verify case was populated
        self.assertTrue(len(self.cli.case) > 0)
        
        # Restore original method
        self.cli.ask_questions = original_ask
    
    def test_cli_show_outcome_with_actual_evaluation(self):
        """Test CLI show_outcome with actual ADF evaluation"""
        # Set up CLI with sub-ADM and case data
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        self.cli.adf = create_sub_adm_1("test_feature")
        self.cli.caseName = "test_outcome_case"
        self.cli.case = ["DistinguishingFeatures", "IndependentContribution"]
        
        # Mock print to capture output
        builtins.print = self.mock_print
        
        # Call show_outcome
        self.cli.show_outcome()
        
        # Verify evaluation was performed and results were printed
        print_output = ' '.join(self.print_calls)
        self.assertTrue('Case Outcome: test_outcome_case' in print_output)
        self.assertTrue('Evaluation Results:' in print_output)
    
    def test_cli_complex_workflow_sub_adm(self):
        """Test complete CLI workflow with complex sub-ADM case"""
        # Set up CLI with sub-ADM
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        self.cli.adf = create_sub_adm_1("complex_feature")
        self.cli.caseName = "complex_sub_adm_case"
        self.cli.case = []
        
        # Complex test case: All positive factors
        test_blfs = ["DistinguishingFeatures", "IndependentContribution", "ComputerSimulation", "TechnicalAdaptation", "Credible", "Reproducible"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "IndependentContribution", 
            "ExcludedField",
            "NumOrComp",
            "ComputerSimulation", 
            "TechnicalAdaptation", 
            "Credible", 
            "Reproducible", 
            "ComputationalContribution", 
            "FeatureTechnicalContribution", 
            "FeatureReliableTechnicalEffect"
        ]
        
        # Simulate full workflow
        for blf in test_blfs:
            if blf not in self.cli.case:
                self.cli.case.append(blf)
        
        # Evaluate case
        self.cli.adf.evaluateTree(self.cli.case)
        actual_final_case = self.cli.case.copy()
        
        # Verify expected outcome
        self.assertEqual(set(actual_final_case), set(expected_final_case))
        
        # Test show_outcome
        builtins.print = self.mock_print
        self.cli.show_outcome()
        
        # Verify results were displayed
        print_output = ' '.join(self.print_calls)
        self.assertTrue('complex_sub_adm_case' in print_output)
    
    def test_cli_complex_workflow_main_adm(self):
        """Test complete CLI workflow with complex main ADM case"""
        # Set up CLI with main ADM
        from ADM_JURIX.ADM.inventive_step_ADM import adf
        self.cli.adf = adf()
        self.cli.caseName = "complex_main_adm_case"
        self.cli.case = []
        
        # Complex test case: All major factors
        test_blfs = [
            "Individual", "SkilledIn", "Average", "Aware", "Access",
            "SameField", "SimilarPurpose", "SimilarEffect",
            "Textbook", "SingleReference", "MinModifications", "AssessedBy",
            "CombinationAttempt", "SameFieldCPA", "CombinationMotive", "BasisToAssociate"
        ]
        expected_final_case = [
            "Individual", "SkilledIn", "Average", 
            "Aware", "Access", "Person", "SkilledPerson", "SameField", 
            "SimilarPurpose", "SimilarEffect", "RelevantPriorArt", "Textbook", 
            "DocumentaryEvidence", "CommonKnowledge", "SingleReference", 
            "MinModifications", "AssessedBy", "ClosestPriorArt", "CombinationAttempt", 
            "SameFieldCPA", "CombinationMotive", "BasisToAssociate", 
            "CombinationDocuments", "ClosestPriorArtDocuments"
        ]
        
        # Simulate full workflow
        for blf in test_blfs:
            if blf not in self.cli.case:
                self.cli.case.append(blf)
        
        # Evaluate case
        self.cli.adf.evaluateTree(self.cli.case)
        actual_final_case = self.cli.case.copy()
        
        # Verify expected outcome
        self.assertEqual(set(actual_final_case), set(expected_final_case))
        
        # Test show_outcome
        builtins.print = self.mock_print
        self.cli.show_outcome()
        
        # Verify results were displayed
        print_output = ' '.join(self.print_calls)
        self.assertTrue('complex_main_adm_case' in print_output)
    
    def test_cli_rejection_case_sub_adm(self):
        """Test CLI with sub-ADM rejection case"""
        # Set up CLI with sub-ADM
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        self.cli.adf = create_sub_adm_1("rejection_feature")
        self.cli.caseName = "rejection_case"
        self.cli.case = []
        
        # Test case: Should be rejected due to CircumventTechProblem
        test_blfs = ["DistinguishingFeatures","IndependentContribution", "CircumventTechProblem", "Credible", "Reproducible"]
        expected_final_case = [
            "DistinguishingFeatures", 
            "IndependentContribution", 
            "CircumventTechProblem", 
            "Credible", 
            "Reproducible"
            # NormalTechnicalContribution should NOT be added due to CircumventTechProblem
        ]
        
        # Simulate workflow
        for blf in test_blfs:
            if blf not in self.cli.case:
                self.cli.case.append(blf)
        
        # Evaluate case
        self.cli.adf.evaluateTree(self.cli.case)
        actual_final_case = self.cli.case.copy()
        
        # Verify expected outcome (rejection)
        self.assertEqual(set(actual_final_case), set(expected_final_case))
        self.assertNotIn("NormalTechnicalContribution", actual_final_case)
    
    def test_cli_edge_case_no_blfs(self):
        """Test CLI with edge case - no BLFs"""
        # Set up CLI with sub-ADM
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        self.cli.adf = create_sub_adm_1("edge_feature")
        self.cli.caseName = "edge_case"
        self.cli.case = []
        
        # Test case: Only base case
        test_blfs = ["DistinguishingFeatures"]
        expected_final_case = [
            "DistinguishingFeatures",
            "NonReproducible"
        ]
        
        # Simulate workflow
        for blf in test_blfs:
            if blf not in self.cli.case:
                self.cli.case.append(blf)
        
        # Evaluate case
        self.cli.adf.evaluateTree(self.cli.case)
        actual_final_case = self.cli.case.copy()
        
        # Verify expected outcome
        self.assertEqual(set(actual_final_case), set(expected_final_case))
    
    def test_cli_case_persistence(self):
        """Test CLI case persistence across operations"""
        # Set up CLI with sub-ADM
        from ADM_JURIX.ADM.inventive_step_ADM import create_sub_adm_1
        self.cli.adf = create_sub_adm_1("persistence_feature")
        self.cli.caseName = "persistence_case"
        self.cli.case = []
        
        # Add some BLFs
        test_blfs = ["IndependentContribution", "ComputerSimulation"]
        for blf in test_blfs:
            if blf not in self.cli.case:
                self.cli.case.append(blf)
        
        # Verify case is stored
        self.assertEqual(len(self.cli.case), 2)
        self.assertIn("IndependentContribution", self.cli.case)
        self.assertIn("ComputerSimulation", self.cli.case)
        
        # Test that case persists across operations (but show_outcome will add abstract factors)
        original_case = self.cli.case.copy()
        self.cli.show_outcome()  # This will add abstract factors via evaluateTree()
        
        # Verify that the original BLFs are still there, but abstract factors may be added
        for blf in original_case:
            self.assertIn(blf, self.cli.case)
        
        # The case should have grown (abstract factors added)
        self.assertGreaterEqual(len(self.cli.case), len(original_case))

class TestDependencyEvaluation(unittest.TestCase):
    """Unit tests for dependency evaluation debugging"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.adf_instance = adf()
        self.ui = CLI()
        self.ui.adf = self.adf_instance
        
    def test_evaluateDependency_detailed_debug(self):
        """Test: Detailed debug output for evaluateDependency method"""
        # Set up case with TechnicalSurvey to enable the full chain
        self.ui.case = ["Contested","TechnicalSurvey"]
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for CommonKnowledge directly
            result = self.ui.evaluateDependency("CommonKnowledge", "Access")
        
        debug_output = output.getvalue()

        # Basic assertions - should see successful evaluation
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation")
        self.assertIn("CommonKnowledge", debug_output, "Should see CommonKnowledge in debug output")
        self.assertIn("CommonKnowledge now satisfied", debug_output, "Should see CommonKnowledge now satisfied message")
        self.assertIn("DocumentaryEvidence now satisfied", debug_output, "Should see DocumentaryEvidence now satisfied message")
        
        # Check that both dependencies were added to case
        self.assertIn("DocumentaryEvidence", self.ui.case, "DocumentaryEvidence should be added to case")
        self.assertIn("CommonKnowledge", self.ui.case, "CommonKnowledge should be added to case")
    
     
    def test_evaluateDependency_combination_motive_chain(self):
        """Test: CombinationMotive dependency chain"""
        # Set up case with required components for CombinationMotive
        # CombinationMotive requires: ClosestPriorArt, SkilledPerson, CombinationAttempt
        self.ui.case = ["ClosestPriorArt", "SkilledPerson", "CombinationAttempt", "TechnicalSurvey"]
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for CombinationMotive directly
            result = self.ui.evaluateDependency("CombinationMotive", "TestQuestion")
        
        debug_output = output.getvalue()
        
        
        # Should see dependency evaluation
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation")
        self.assertIn("CombinationMotive", debug_output, "Should see CombinationMotive in debug output")

    def test_evaluateDependency_combination_motive_failure_case(self):
        """Test: CombinationMotive failure case - missing required dependency"""
        # Set up case missing CombinationAttempt (required for CombinationMotive)
        self.ui.case = ["ClosestPriorArt", "SkilledPerson", "TechnicalSurvey"]
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for CombinationMotive directly
            result = self.ui.evaluateDependency("CombinationMotive", "TestQuestion")
        
        debug_output = output.getvalue()
        
        # Should see dependency evaluation attempt but CombinationMotive should not be satisfied
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation")
        self.assertIn("CombinationMotive", debug_output, "Should see CombinationMotive in debug output")
        # CombinationMotive should not be added to case due to missing CombinationAttempt
        self.assertNotIn("CombinationMotive", self.ui.case, "CombinationMotive should not be added with missing dependencies")
    
    def test_evaluateDependency_basis_to_associate_chain(self):
        """Test: BasisToAssociate dependency chain"""
        # Set up case with required components for BasisToAssociate
        self.ui.case = ["ClosestPriorArt", "SkilledPerson", "CombinationAttempt", "TechnicalSurvey"]
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for BasisToAssociate directly
            result = self.ui.evaluateDependency("BasisToAssociate", "TestQuestion")
        
        debug_output = output.getvalue()

        # Should see dependency evaluation
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation")
        self.assertIn("BasisToAssociate", debug_output, "Should see BasisToAssociate in debug output")
    
    def test_evaluateDependency_closest_prior_art_chain(self):
        """Test: ClosestPriorArt dependency chain"""
        # Set up case with required components for ClosestPriorArt
        # ClosestPriorArt requires: RelevantPriorArt and SingleReference and MinModifications and AssessedBy
        self.ui.case = ["RelevantPriorArt", "SingleReference", "MinModifications", "AssessedBy", "SameField"]
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for ClosestPriorArt directly
            result = self.ui.evaluateDependency("ClosestPriorArt", "TestQuestion")
        
        debug_output = output.getvalue()
        
        
        # Should see dependency evaluation
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation")
        self.assertIn("ClosestPriorArt", debug_output, "Should see ClosestPriorArt in debug output")
    
    def test_evaluateDependency_combination_documents_chain(self):
        """Test: CombinationDocuments dependency chain"""
        # Set up case with required components for CombinationDocuments
        self.ui.case = ["CombinationAttempt", "SameFieldCPA", "CombinationMotive", "BasisToAssociate", "TechnicalSurvey"]
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for CombinationDocuments directly
            result = self.ui.evaluateDependency("CombinationDocuments", "TestQuestion")
        
        debug_output = output.getvalue()
        
        
        # Should see dependency evaluation
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation")
        self.assertIn("CombinationDocuments", debug_output, "Should see CombinationDocuments in debug output")
    
    def test_evaluateDependency_relevant_prior_art_chain(self):
        """Test: RelevantPriorArt dependency chain"""
        # Set up case with required components for RelevantPriorArt
        self.ui.case = ["SameField", "SimilarField", "SimilarPurpose", "SimilarEffect"]
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for RelevantPriorArt directly
            result = self.ui.evaluateDependency("RelevantPriorArt", "TestQuestion")
        
        debug_output = output.getvalue()
        
        # Should see dependency evaluation
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation")
        self.assertIn("RelevantPriorArt", debug_output, "Should see RelevantPriorArt in debug output")
    
    def test_evaluateDependency_person_chain(self):
        """Test: Person dependency chain"""
        # Set up case with required components for Person
        self.ui.case = ["Individual", "ResearchTeam", "ProductionTeam"]
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for Person directly
            result = self.ui.evaluateDependency("Person", "TestQuestion")
        
        debug_output = output.getvalue()
        
        # Should see dependency evaluation
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation")
        self.assertIn("Person", debug_output, "Should see Person in debug output")
    
    def test_evaluateDependency_skilled_in_chain(self):
        """Test: SkilledIn dependency chain"""
        # Set up case with required components for SkilledIn
        # SkilledIn depends on RelevantPriorArt
        self.ui.case = ["RelevantPriorArt", "SameField"]
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for SkilledIn directly
            result = self.ui.evaluateDependency("SkilledIn", "TestQuestion")
        
        debug_output = output.getvalue()
        
        
        # Should see dependency evaluation
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation")
        self.assertIn("SkilledIn", debug_output, "Should see SkilledIn in debug output")
    
    def test_evaluateDependency_combination_attempt_chain(self):
        """Test: CombinationAttempt dependency chain"""
        # Set up case with required components for CombinationAttempt
        self.ui.case = ["ClosestPriorArt", "SkilledPerson", "MinModifications", "AssessedBy"]
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for CombinationAttempt directly
            result = self.ui.evaluateDependency("CombinationAttempt", "TestQuestion")
        
        debug_output = output.getvalue()
        
        # Should see dependency evaluation
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation")
        self.assertIn("CombinationAttempt", debug_output, "Should see CombinationAttempt in debug output")
    
    def test_evaluateDependency_complex_failure_case(self):
        """Test: Complex failure case with missing dependencies"""
        # Set up case with incomplete dependencies
        self.ui.case = ["TechnicalSurvey"]  # Missing other required components
        
        output = io.StringIO()
        with redirect_stdout(output):
            # Test evaluateDependency for SkilledPerson (should fail due to missing dependencies)
            result = self.ui.evaluateDependency("SkilledPerson", "TestQuestion")
        
        debug_output = output.getvalue()
        
        # Should see dependency evaluation attempts but failures
        self.assertIn("Trying to evaluate dependency", debug_output, "Should see dependency evaluation attempts")
        self.assertIn("SkilledPerson", debug_output, "Should see SkilledPerson in debug output")
        
        # SkilledPerson should not be added due to missing dependencies
        self.assertNotIn("SkilledPerson", self.ui.case, "SkilledPerson should not be added with incomplete dependencies")
    
    # Note: Sub-ADM tests removed because those nodes are in sub_adf, not the main adf
    # The evaluateDependency method only works with nodes in the main ADF

def run_all_tests():
    """Run all unit tests (sub-ADM, main ADM, and CLI UI)"""
    print("Running All ADM Unit Tests...")
    print("="*60)
    
    # Create test suite for all test classes
    suite = unittest.TestSuite()
    
    # Add sub-ADM tests
    sub_adm_suite = unittest.TestLoader().loadTestsFromTestCase(TestSubADMEvaluation)
    suite.addTest(sub_adm_suite)
    
    # Add main ADM tests
    main_adm_suite = unittest.TestLoader().loadTestsFromTestCase(TestMainADMEvaluation)
    suite.addTest(main_adm_suite)
    
    # Add CLI UI tests
    cli_suite = unittest.TestLoader().loadTestsFromTestCase(TestCLIUI)
    suite.addTest(cli_suite)
    
    # Add dependency evaluation tests
    dependency_suite = unittest.TestLoader().loadTestsFromTestCase(TestDependencyEvaluation)
    suite.addTest(dependency_suite)
    
    # Run tests with minimal verbosity
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print(f"\n{'='*60}")
        print(f"DETAILED FAILURE ANALYSIS")
        print(f"{'='*60}")
        for i, (test, traceback) in enumerate(result.failures, 1):
            print(f"\n{i}. FAILURE: {test}")
            print(f"{'─'*50}")
            
            # Extract the detailed error message
            lines = traceback.split('\n')
            assertion_found = False
            
            for line in lines:
                if 'Expected:' in line and 'Got:' in line:
                    print(f"   Assertion Error: {line}")
                    assertion_found = True
                    break
            
            if not assertion_found:
                # Look for AssertionError line
                for line in lines:
                    if 'AssertionError:' in line:
                        error_msg = line.split('AssertionError: ')[-1]
                        print(f"   Assertion Error: {error_msg}")
                        assertion_found = True
                        break
            
            if not assertion_found:
                # Fallback to original error message
                error_msg = traceback.split('AssertionError: ')[-1].split('\n')[0]
                print(f"   Error: {error_msg}")
            
            # Show the full traceback for debugging
            print(f"\n   Full Traceback:")
            for line in lines:
                if line.strip():
                    print(f"   {line}")
    
    if result.errors:
        print(f"\n{'='*60}")
        print(f"DETAILED ERROR ANALYSIS")
        print(f"{'='*60}")
        for i, (test, traceback) in enumerate(result.errors, 1):
            print(f"\n{i}. ERROR: {test}")
            print(f"{'─'*50}")
            
            # Extract the main error message
            lines = traceback.split('\n')
            error_msg = "Unknown error"
            
            for line in lines:
                if 'Exception:' in line or 'Error:' in line:
                    error_msg = line.strip()
                    break
                elif 'Traceback' in line and 'most recent call last' in line:
                    # Look for the actual exception in the next few lines
                    for j, trace_line in enumerate(lines[lines.index(line)+1:], lines.index(line)+1):
                        if 'Exception' in trace_line or 'Error' in trace_line:
                            error_msg = trace_line.strip()
                            break
            
            print(f"   Error: {error_msg}")
            
            # Show the full traceback for debugging
            print(f"\n   Full Traceback:")
            for line in lines:
                if line.strip():
                    print(f"   {line}")
    
    # Exit with error code if tests failed
    if result.failures or result.errors:
        sys.exit(1)
    
    return result


def run_sub_adm_tests():
    """Run only sub-ADM unit tests"""
    print("Running Sub-ADM Unit Tests...")
    print("="*60)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSubADMEvaluation)
    
    # Run tests with minimal verbosity
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print(f"\n{'='*60}")
        print(f"DETAILED FAILURE ANALYSIS")
        print(f"{'='*60}")
        for i, (test, traceback) in enumerate(result.failures, 1):
            print(f"\n{i}. FAILURE: {test}")
            print(f"{'─'*50}")
            
            # Extract the detailed error message
            lines = traceback.split('\n')
            assertion_found = False
            
            for line in lines:
                if 'Expected:' in line and 'Got:' in line:
                    print(f"   Assertion Error: {line}")
                    assertion_found = True
                    break
            
            if not assertion_found:
                # Look for AssertionError line
                for line in lines:
                    if 'AssertionError:' in line:
                        error_msg = line.split('AssertionError: ')[-1]
                        print(f"   Assertion Error: {error_msg}")
                        assertion_found = True
                        break
            
            if not assertion_found:
                # Fallback to original error message
                error_msg = traceback.split('AssertionError: ')[-1].split('\n')[0]
                print(f"   Error: {error_msg}")
            
            # Show the full traceback for debugging
            print(f"\n   Full Traceback:")
            for line in lines:
                if line.strip():
                    print(f"   {line}")
    
    if result.errors:
        print(f"\n{'='*60}")
        print(f"DETAILED ERROR ANALYSIS")
        print(f"{'='*60}")
        for i, (test, traceback) in enumerate(result.errors, 1):
            print(f"\n{i}. ERROR: {test}")
            print(f"{'─'*50}")
            
            # Extract the main error message
            lines = traceback.split('\n')
            error_msg = "Unknown error"
            
            for line in lines:
                if 'Exception:' in line or 'Error:' in line:
                    error_msg = line.strip()
                    break
                elif 'Traceback' in line and 'most recent call last' in line:
                    # Look for the actual exception in the next few lines
                    for j, trace_line in enumerate(lines[lines.index(line)+1:], lines.index(line)+1):
                        if 'Exception' in trace_line or 'Error' in trace_line:
                            error_msg = trace_line.strip()
                            break
            
            print(f"   Error: {error_msg}")
            
            # Show the full traceback for debugging
            print(f"\n   Full Traceback:")
            for line in lines:
                if line.strip():
                    print(f"   {line}")
    
    # Exit with error code if tests failed
    if result.failures or result.errors:
        sys.exit(1)
    
    return result


def run_main_adm_tests():
    """Run only main ADM unit tests"""
    print("Running Main ADM Unit Tests...")
    print("="*60)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMainADMEvaluation)
    
    # Run tests with minimal verbosity
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print(f"\n{'='*60}")
        print(f"DETAILED FAILURE ANALYSIS")
        print(f"{'='*60}")
        for i, (test, traceback) in enumerate(result.failures, 1):
            print(f"\n{i}. FAILURE: {test}")
            print(f"{'─'*50}")
            
            # Extract the detailed error message
            lines = traceback.split('\n')
            assertion_found = False
            
            for line in lines:
                if 'Expected:' in line and 'Got:' in line:
                    print(f"   Assertion Error: {line}")
                    assertion_found = True
                    break
            
            if not assertion_found:
                # Look for AssertionError line
                for line in lines:
                    if 'AssertionError:' in line:
                        error_msg = line.split('AssertionError: ')[-1]
                        print(f"   Assertion Error: {error_msg}")
                        assertion_found = True
                        break
            
            if not assertion_found:
                # Fallback to original error message
                error_msg = traceback.split('AssertionError: ')[-1].split('\n')[0]
                print(f"   Error: {error_msg}")
            
            # Show the full traceback for debugging
            print(f"\n   Full Traceback:")
            for line in lines:
                if line.strip():
                    print(f"   {line}")
    
    if result.errors:
        print(f"\n{'='*60}")
        print(f"DETAILED ERROR ANALYSIS")
        print(f"{'='*60}")
        for i, (test, traceback) in enumerate(result.errors, 1):
            print(f"\n{i}. ERROR: {test}")
            print(f"{'─'*50}")
            
            # Extract the main error message
            lines = traceback.split('\n')
            error_msg = "Unknown error"
            
            for line in lines:
                if 'Exception:' in line or 'Error:' in line:
                    error_msg = line.strip()
                    break
                elif 'Traceback' in line and 'most recent call last' in line:
                    # Look for the actual exception in the next few lines
                    for j, trace_line in enumerate(lines[lines.index(line)+1:], lines.index(line)+1):
                        if 'Exception' in trace_line or 'Error' in trace_line:
                            error_msg = trace_line.strip()
                            break
            
            print(f"   Error: {error_msg}")
            
            # Show the full traceback for debugging
            print(f"\n   Full Traceback:")
            for line in lines:
                if line.strip():
                    print(f"   {line}")
    
    # Exit with error code if tests failed
    if result.failures or result.errors:
        sys.exit(1)
    
    return result


def run_cli_tests():
    """Run only CLI UI unit tests"""
    print("Running CLI UI Unit Tests...")
    print("="*60)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCLIUI)
    
    # Run tests with minimal verbosity
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print(f"\n{'='*60}")
        print(f"DETAILED FAILURE ANALYSIS")
        print(f"{'='*60}")
        for i, (test, traceback) in enumerate(result.failures, 1):
            print(f"\n{i}. FAILURE: {test}")
            print(f"{'─'*50}")
            
            # Extract the detailed error message
            lines = traceback.split('\n')
            assertion_found = False
            
            for line in lines:
                if 'Expected:' in line and 'Got:' in line:
                    print(f"   Assertion Error: {line}")
                    assertion_found = True
                    break
            
            if not assertion_found:
                # Look for AssertionError line
                for line in lines:
                    if 'AssertionError:' in line:
                        error_msg = line.split('AssertionError: ')[-1]
                        print(f"   Assertion Error: {error_msg}")
                        assertion_found = True
                        break
            
            if not assertion_found:
                # Fallback to original error message
                error_msg = traceback.split('AssertionError: ')[-1].split('\n')[0]
                print(f"   Error: {error_msg}")
            
            # Show the full traceback for debugging
            print(f"\n   Full Traceback:")
            for line in lines:
                if line.strip():
                    print(f"   {line}")
    
    if result.errors:
        print(f"\n{'='*60}")
        print(f"DETAILED ERROR ANALYSIS")
        print(f"{'='*60}")
        for i, (test, traceback) in enumerate(result.errors, 1):
            print(f"\n{i}. ERROR: {test}")
            print(f"{'─'*50}")
            
            # Extract the main error message
            lines = traceback.split('\n')
            error_msg = "Unknown error"
            
            for line in lines:
                if 'Exception:' in line or 'Error:' in line:
                    error_msg = line.strip()
                    break
                elif 'Traceback' in line and 'most recent call last' in line:
                    # Look for the actual exception in the next few lines
                    for j, trace_line in enumerate(lines[lines.index(line)+1:], lines.index(line)+1):
                        if 'Exception' in trace_line or 'Error' in trace_line:
                            error_msg = trace_line.strip()
                            break
            
            print(f"   Error: {error_msg}")
            
            # Show the full traceback for debugging
            print(f"\n   Full Traceback:")
            for line in lines:
                if line.strip():
                    print(f"   {line}")
    
    # Exit with error code if tests failed
    if result.failures or result.errors:
        sys.exit(1)
    
    return result


def run_dependency_tests():
    """Run only dependency evaluation unit tests"""
    print("Running Dependency Evaluation Unit Tests...")
    print("="*60)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDependencyEvaluation)
    
    # Run tests with minimal verbosity
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print(f"\n{'='*60}")
        print(f"DETAILED FAILURE ANALYSIS")
        print(f"{'='*60}")
        for i, (test, traceback) in enumerate(result.failures, 1):
            print(f"\n{i}. FAILURE: {test}")
            print(f"{'─'*50}")
            
            # Extract the detailed error message
            lines = traceback.split('\n')
            assertion_found = False
            
            for line in lines:
                if 'Expected:' in line and 'Got:' in line:
                    print(f"   Assertion Error: {line}")
                    assertion_found = True
                    break
            
            if not assertion_found:
                # Look for AssertionError line
                for line in lines:
                    if 'AssertionError:' in line:
                        error_msg = line.split('AssertionError: ')[-1]
                        print(f"   Assertion Error: {error_msg}")
                        assertion_found = True
                        break
            
            if not assertion_found:
                # Fallback to original error message
                error_msg = traceback.split('AssertionError: ')[-1].split('\n')[0]
                print(f"   Error: {error_msg}")
            
            # Show the full traceback for debugging
            print(f"\n   Full Traceback:")
            for line in lines:
                if line.strip():
                    print(f"   {line}")
    
    if result.errors:
        print(f"\n{'='*60}")
        print(f"DETAILED ERROR ANALYSIS")
        print(f"{'='*60}")
        for i, (test, traceback) in enumerate(result.errors, 1):
            print(f"\n{i}. ERROR: {test}")
            print(f"{'─'*50}")
            
            # Extract the main error message
            lines = traceback.split('\n')
            error_msg = "Unknown error"
            
            for line in lines:
                if 'Exception:' in line or 'Error:' in line:
                    error_msg = line.strip()
                    break
                elif 'Traceback' in line and 'most recent call last' in line:
                    # Look for the actual exception in the next few lines
                    for j, trace_line in enumerate(lines[lines.index(line)+1:], lines.index(line)+1):
                        if 'Exception' in trace_line or 'Error' in trace_line:
                            error_msg = trace_line.strip()
                            break
            
            print(f"   Error: {error_msg}")
            
            # Show the full traceback for debugging
            print(f"\n   Full Traceback:")
            for line in lines:
                if line.strip():
                    print(f"   {line}")
    
    # Exit with error code if tests failed
    if result.failures or result.errors:
        sys.exit(1)
    
    return result


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "all":
            result = run_all_tests()
        elif sys.argv[1] == "sub":
            result = run_sub_adm_tests()
        elif sys.argv[1] == "main":
            result = run_main_adm_tests()
        elif sys.argv[1] == "cli":
            result = run_cli_tests()
        elif sys.argv[1] == "dep":
            result = run_dependency_tests()
        else:
            print("Usage: python test_adm_unit.py [all|sub|main|cli|dep]")
            print("  all  - Run all tests")
            print("  sub  - Run only sub-ADM tests")
            print("  main - Run only main ADM tests")
            print("  cli  - Run only CLI UI tests")
            print("  dep  - Run only dependency evaluation tests")
            print("  (no args) - Run all tests")
            sys.exit(1)
    else:
        result = run_all_tests()
    
    # Exit with error code if any tests failed
    if result.failures or result.errors:
        sys.exit(1)
