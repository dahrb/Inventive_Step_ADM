"""
ADM Command Line Interface
"""

import os
import sys
import shlex
from MainClasses import *
import inventive_step_ADM


class CLI:
    def __init__(self):
        self.case = []
        self.adf = inventive_step_ADM.adf()
        self.cases = inventive_step_ADM.cases()
        self.caseName = None
        
    def main_menu(self):
        """Main menu with options"""
        self.query_domain()
    
    def query_domain(self):
        """Query the domain by answering questions"""
        print("\n" + "="*50)
        print("Query Domain")
        print("="*50)
        
        self.caseName = 'test'#input("Enter case name: ").strip()
        if not self.caseName:
            print("No case name provided.")
            return

        # Reset case and start questioning
        self.case = []
        self.ask_questions()
        
        print(f"Case: {self.case}")

        return

    def ask_questions(self):
        """Ask questions to build the case"""
        print("\nAnswer questions to build your case...")
        
        # Get a copy of nodes and question order
        nodes = self.adf.nodes.copy()
        question_order = self.adf.questionOrder.copy() if self.adf.questionOrder else []

        
        if question_order != []:
            while question_order:
                question_order, nodes = self.questiongen(question_order, nodes)
        
        #NO OPTION IF QUESTION ORDER NOT SPECIFIED
        else:
            print("No question order specified")

        self.show_outcome()

    def questiongen(self, question_order, nodes):
        """
        Generates questions based on the question order and current nodes
        """
        if not question_order:
            return question_order, nodes
        
        current_question = question_order[0]
        
        # Check if this is a question instantiator first
        if current_question in self.adf.question_instantiators:
            instantiator = self.adf.question_instantiators[current_question]
            
            # Check if this question instantiator  has a dependency
            if instantiator.get('dependency_node'):
                # Check if dependency is satisfied
                # Handle both single string and list
                dependency_node = instantiator['dependency_node']

                if isinstance(dependency_node, str):
                    dependency_node = [dependency_node]
                
                # Check if ALL dependencies are satisfied
                all_dependencies_satisfied = True
                for dependency_node_name in dependency_node:
                    if dependency_node_name not in self.case:
                        # Try to evaluate the dependency
                        print(f" Trying to evaluate dependency {dependency_node_name} for {current_question}")
                        if not self.evaluateDependency(dependency_node_name, current_question):
                            # Check again if it's now in the case after evaluation
                            if dependency_node_name not in self.case:
                                all_dependencies_satisfied = False
                                break
                
                if not all_dependencies_satisfied:
                    # Dependency cannot be satisfied, skip permanently
                    print(f"⚠️  Skipping {current_question} - dependencies cannot be satisfied")
                    question_order.pop(0)
                    return self.questiongen(question_order, nodes)
            
            # At this point, either no dependency or dependency is satisfied
            # Process the question instantiator
            x = self.questionHelper(None, current_question)
            if x == 'Done':
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
            else:
                # Any other return value means there's an issue, skip permanently
                print(f"⚠️  Skipping {current_question} - processing failed")
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
        
        # Check if this is a regular node (including DependentBLF, EvaluationBLF, and SubADMBLF)
        elif current_question in self.adf.nodes:
            current_node = self.adf.nodes[current_question]
            
            # Check if this is a DependentBLF
            if hasattr(current_node, 'checkDependency') and not hasattr(current_node, 'evaluateSubADMs'):
                return self.handleDependentBLF(current_question, current_node, question_order, nodes)
            
            # Check if this is a SubADMBLF
            elif hasattr(current_node, 'evaluateSubADMs'):
                return self.handleSubADMBLF(current_question, current_node, question_order, nodes)
            
            # Check if this is an EvaluationBLF
            elif hasattr(current_node, 'evaluateResults'):
                return self.handleEvaluationBLF(current_question, current_node, question_order, nodes)
            
            else:
                #process regular blf
                x = self.questionHelper(current_node, current_question)
                if x == 'Done':
                    question_order.pop(0)
                    return self.questiongen(question_order, nodes)
                elif x == 'Invalid':
                    # Invalid answer, skip this question permanently
                    print(f"⚠️  Skipping {current_question} - too many invalid answers")
                    question_order.pop(0)
                    return self.questiongen(question_order, nodes)
                else:
                    return question_order, nodes
                    
        elif current_question in self.adf.information_questions:
            # This is an information question
            question_text = self.adf.information_questions[current_question]
            answer = input(f"{question_text}: ").strip()
            
            # Store the answer as a fact without adding to case
            if hasattr(self.adf, 'setFact'):
                self.adf.setFact('INFORMATION', current_question, answer)
            
            # Remove from question order and continue
            question_order.pop(0)
            return self.questiongen(question_order, nodes)
        else:
            question_order.pop(0)
            return self.questiongen(question_order, nodes)
        
  
    def questionHelper(self, current_node, current_question):
        """
        Helper method to handle individual questions
        """
        if current_node is None:
            # This is a question instantiator
            instantiator = self.adf.question_instantiators[current_question]
            
            # Note: Dependencies are already checked in questiongen, so we can proceed directly
            
            # Resolve any template variables in the question using inherited facts
            question_text = instantiator['question']
            resolved_question = self.resolve_question_template(question_text)
            
            # If there's a dependency, try to get inherited facts from the dependency node
            if instantiator.get('dependency_node'):
                dependency_node_name = instantiator['dependency_node']
                if hasattr(self.adf, 'getInheritedFacts'):
                    # Handle both single string and list of dependencies
                    if isinstance(dependency_node_name, str):
                        dependency_nodes = [dependency_node_name]
                    else:
                        dependency_nodes = dependency_node_name
                    
                    # Collect facts from all dependency nodes
                    inherited_facts = {}
                    for dep_node in dependency_nodes:
                        if isinstance(dep_node, str):
                            dep_facts = self.adf.getInheritedFacts(dep_node, self.case)
                            if isinstance(dep_facts, dict):
                                inherited_facts.update(dep_facts)
                    
                    if inherited_facts:
                        # Replace any placeholders in the question with inherited facts
                        for fact_name, value in inherited_facts.items():
                            placeholder = "{" + fact_name + "}"
                            if placeholder in resolved_question:
                                resolved_question = resolved_question.replace(placeholder, str(value))
            
            print(f"\n{resolved_question}")
            # Show available answers
            answers = list(instantiator['blf_mapping'].keys())
            for i, answer in enumerate(answers, 1):
                print(f"{i}. {answer}")
            
            # Get user choice
            while True:
                try:
                    choice = int(input("Choose an answer (enter number): ")) - 1
                    if 0 <= choice < len(answers):
                        selected_answer = answers[choice]
                        break
                    else:
                        print("Invalid choice. Please try again.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
            
            # Instantiate the corresponding BLF(s)
            blf_names = instantiator['blf_mapping'][selected_answer]
            if isinstance(blf_names, str):
                blf_names = [blf_names]
            for blf_name in blf_names:
                # Skip empty string BLFs - they're just placeholders
                if blf_name == "":
                    continue
                
                # Check if this BLF has reject conditions before adding to case
                if blf_name in self.adf.nodes and hasattr(self.adf.nodes[blf_name], 'acceptance') and self.adf.nodes[blf_name].acceptance:
                    # Check if any acceptance condition contains 'reject'
                    has_reject = any('reject' in condition for condition in self.adf.nodes[blf_name].acceptance)
                    if has_reject:
                        print(f"Note: {blf_name} has reject conditions and will not be added to case")
                        continue
                
                # Add the BLF to the case (only if no reject conditions)
                if blf_name not in self.case:
                    self.case.append(blf_name)
                else:
                    pass
                
                # Ask factual ascription questions if configured
                if instantiator.get('factual_ascription') and blf_name in instantiator['factual_ascription']:
                    factual_questions = instantiator['factual_ascription'][blf_name]
                    for fact_name, question in factual_questions.items():
                        answer = input(f"{question}: ").strip()
                        if answer:
                            self.adf.setFact(blf_name, fact_name, answer)
            
            return 'Done'
        else:
            # This is a regular node
            
            # Handle regular nodes with questions
            if hasattr(current_node, 'question') and current_node.question:
                question_text = self.resolve_question_template(current_node.question)
                            
                # Ask the question with retry loop
                while True:
                    answer = input(f"{question_text}\nAnswer (y/n): ").strip().lower()
                    
                    if answer in ['y', 'yes']:
                        # Check if this node has reject conditions before adding to case
                        if hasattr(self.adf.nodes[current_question], 'acceptance') and self.adf.nodes[current_question].acceptance:
                            # Check if any acceptance condition contains 'reject'
                            has_reject = any('reject' in condition for condition in self.adf.nodes[current_question].acceptance)
                            if has_reject:
                                print(f"Note: {current_question} has reject conditions and will not be added to case")
                            else:
                                # No reject conditions, safe to add
                                if current_question not in self.case:
                                    self.case.append(current_question)
                        else:
                            # No acceptance conditions, safe to add
                            if current_question not in self.case:
                                self.case.append(current_question)
                        return 'Done'
                    elif answer in ['n', 'no']:
                        return 'Done'
                    else:
                        print("Invalid answer, please answer y/n")
                        # Don't return 'Invalid' - just continue the loop to ask again
            else:
                # Check if this node has reject conditions before adding to case
                if hasattr(self.adf.nodes[current_question], 'acceptance') and self.adf.nodes[current_question].acceptance:
                    # Check if any acceptance condition contains 'reject'
                    has_reject = any('reject' in condition for condition in self.adf.nodes[current_question].acceptance)
                    if has_reject:
                        print(f"Note: {current_question} has reject conditions and will not be added to case")
                    else:
                        # No reject conditions, safe to add
                        if current_question not in self.case:
                            self.case.append(current_question)
                else:
                    # No acceptance conditions, safe to add
                    if current_question not in self.case:
                        self.case.append(current_question)
                return 'Done'

    def handleDependentBLF(self, current_question, current_node, question_order, nodes):
        """Handles the processing of a DependentBLF node"""
        
        # Check if ALL dependencies are satisfied
        if current_node.checkDependency(self.adf, self.case):
            # All dependencies satisfied, process the DependentBLF
            resolved_question = current_node.resolveQuestion(self.adf, self.case)
            x = self.questionHelper(current_node, current_question)
            if x == 'Done':
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
            else:
                return question_order, nodes
        else:

            # Try to evaluate missing dependencies
            dependency_node = current_node.dependency_node
            all_dependencies_satisfied = True
            
            for dependency_node_name in dependency_node:
                if dependency_node_name not in self.case:
                    if not self.evaluateDependency(dependency_node_name, current_question):
                        all_dependencies_satisfied = False
                        break
            
            if all_dependencies_satisfied:
                # All dependencies now satisfied, process the DependentBLF
                resolved_question = current_node.resolveQuestion(self.adf, self.case)
                x = self.questionHelper(current_node, current_question)
                if x == 'Done':
                    question_order.pop(0)
                    return self.questiongen(question_order, nodes)
                else:
                    return question_order, nodes
            else:
                # Dependencies cannot be satisfied, skip
                print(f"⚠️  Skipping {current_question} - dependencies cannot be satisfied")
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
                
    def handleEvaluationBLF(self, current_question, current_node, question_order, nodes):
        """
        Handles the processing of an EvaluationBLF node
        
        Parameters
        ----------
        current_question : str
            the name of the current question being processed
        current_node : EvaluationBLF
            the EvaluationBLF node to process
        question_order : list
            the current question order
        nodes : dict
            the current nodes dictionary
            
        Returns
        -------
        tuple: (question_order, nodes) - the updated question order and nodes
        """
        # Call the evaluateResults method to process the evaluation
        evaluation_result = current_node.evaluateResults(self.adf)
        
        if evaluation_result:
            # Evaluation was successful, add to case
            if current_question not in self.case:
                self.case.append(current_question)
            else:
                pass
        else:
            # Evaluation failed, don't add to case
            pass
        
        # Remove from question order and continue
        question_order.pop(0)
        return self.questiongen(question_order, nodes)

    def handleSubADMBLF(self, current_question, current_node, question_order, nodes):
        """
        Handles the processing of a SubADMBLF node with dependency checking
        
        Parameters
        ----------
        current_question : str
            the name of the current question being processed
        current_node : SubADMBLF
            the SubADMBLF node to process
        question_order : list
            the current question order
        nodes : dict
            the current nodes dictionary
            
        Returns
        -------
        tuple: (question_order, nodes) - the updated question order and nodes
        """
        # Check if ALL dependencies are satisfied
        if current_node.checkDependency(self.adf, self.case):
            # All dependencies satisfied, process the SubADMBLF
            sub_adm_result = current_node.evaluateSubADMs(self)
            
            if sub_adm_result:
                # Sub-ADM evaluation was successful, add to case
                if current_question not in self.case:
                    self.case.append(current_question)
                else:
                    pass
            
            # Remove from question order and continue
            question_order.pop(0)
            return self.questiongen(question_order, nodes)
        else:
            # Try to evaluate missing dependencies
            dependency_node = current_node.dependency_node
            all_dependencies_satisfied = True
            
            for dependency_node_name in dependency_node:
                if dependency_node_name not in self.case:
                    if not self.evaluateDependency(dependency_node_name, current_question):
                        all_dependencies_satisfied = False
                        break
            
            if all_dependencies_satisfied:
                # All dependencies now satisfied, process the SubADMBLF
                sub_adm_result = current_node.evaluateSubADMs(self)
                
                if sub_adm_result:
                    # Sub-ADM evaluation was successful, add to case
                    if current_question not in self.case:
                        self.case.append(current_question)
                    else:
                        pass
                
                # Remove from question order and continue
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
            else:
                # Dependencies cannot be satisfied, skip
                print(f"⚠️  Skipping {current_question} - dependencies cannot be satisfied")
                question_order.pop(0)
                return self.questiongen(question_order, nodes)

    def evaluateDependency(self, dependency_node_name, current_question):
        """Helper method to evaluate a dependency node and add it to case if satisfied"""
        
        # Handle multiple dependencies if passed as a list
        if isinstance(dependency_node_name, list):
            all_satisfied = True
            for dep_node in dependency_node_name:
                if not self.evaluateDependency(dep_node, current_question):
                    all_satisfied = False
            return all_satisfied
        
        dependency_node = self.adf.nodes[dependency_node_name]
        
        print(f" Trying to evaluate dependency {dependency_node_name} for {current_question}")
        
        # Check if dependency node has acceptance conditions and can be evaluated
        if hasattr(dependency_node, 'acceptance') and dependency_node.acceptance:
            try:
                # FIRST: Ensure all child dependencies are evaluated (but don't require them to be satisfied)
                if hasattr(dependency_node, 'children') and dependency_node.children:
                    print(f"  📋 {dependency_node_name} has children: {dependency_node.children}")
                    for child_name in dependency_node.children:
                        if child_name not in self.case:
                            print(f"    🔍 Evaluating child dependency: {child_name}")
                            child_node = self.adf.nodes[child_name]
                            if hasattr(child_node, 'acceptance') and child_node.acceptance:
                                # Recursively evaluate this child (but don't require it to succeed)
                                self.evaluateDependency(child_name, f"child of {dependency_node_name}")
                        else:
                            print(f"    ⚠️  Child {child_name} has no acceptance conditions")
                
                # NOW evaluate the dependency node itself
                print(f"  ✅ Children evaluated, now evaluating {dependency_node_name}")
                
                # Temporarily set the case on the ADF object for evaluation
                original_case = getattr(self.adf, 'case', None)
                self.adf.case = self.case.copy()
                
                # Reset counter for evaluation
                self.adf.counter = -1
                evaluation_result = self.adf.evaluateNode(dependency_node)

                # Restore the original case on the ADF object
                if original_case is not None:
                    self.adf.case = original_case
                else:
                    delattr(self.adf, 'case')
                
                if evaluation_result:
                    # Dependency node can be satisfied, add it to case
                    if dependency_node_name not in self.case:
                        self.case.append(dependency_node_name)
                        print(f"✅ Added {dependency_node_name} to case")
                    
                    print(f"✅ Dependency {dependency_node_name} now satisfied for {current_question}")
                    return True
                else:
                    # Dependency node cannot be satisfied
                    print(f"⚠️  Dependency {dependency_node_name} cannot be satisfied for {current_question}")
                    return False
                    
            except Exception as e:
                # Restore the original case on the ADF object in case of error
                if original_case is not None:
                    self.adf.case = original_case
                else:
                    delattr(self.adf, 'case')
                print(f"⚠️  Error evaluating dependency {dependency_node_name} for {current_question}: {e}")
                return False
        else:
            # Dependency node has no acceptance conditions, can't be evaluated
            print(f"⚠️  Dependency {dependency_node_name} has no acceptance conditions for {current_question}")
            return False

    def resolve_question_template(self, question_text):
        """
        Resolves template variables in question text using collected facts
        """
        # Use the ADF's template resolution method
        return self.adf.resolveQuestionTemplate(question_text)

    def show_outcome(self):
        """Show the evaluation outcome"""
        print("\n" + "="*50)
        print(f"Case Outcome: {self.caseName}")
        print("="*50)
        
        try:
            # Check if statements are already available from previous evaluation
            if hasattr(self.adf, 'statements') and self.adf.statements:
                statements = self.adf.statements
            else:
                # Only evaluate if statements are not available
                statements = self.adf.evaluateTree(self.case)
            
            print("Evaluation Results:")
            for i, statement in enumerate(statements, 1):
                print(f"{i}. {statement}")
        except Exception as e:
            print(f"Error evaluating case: {e}")
        
        # Visualize domain after outcome has been reached
        try:
            self.visualize_domain()
        except Exception as e:
            print(f"Error generating visualization after outcome: {e}")
    
    def visualize_domain(self):
        """Visualize the domain as a graph"""
        print("\n" + "="*50)
        print("Visualize Domain")
        print("="*50)
        
        try:
            # Determine filename based on whether we have a case
            if self.caseName and self.case:
                filename = f"{self.caseName}.png"
                # Visualize with case data to show accepted/rejected nodes in color
                # Visualize the network
                print("\nGenerating visualization...")
                try:
                    # Use the comprehensive visualization that includes sub-ADMs
                    G = self.adf.visualiseNetworkWithSubADMs(self.case)
                    
                    # Save the visualization
                    filename = f"{self.caseName}.png"
                    G.write_png(filename)
                    print(f"Visualization saved as {filename}")
                    try:
                        abs_path = os.path.abspath(filename)
                        print(f"ADM_VISUALIZATION:{abs_path}")
                        sys.stdout.flush()
                    except Exception:
                        pass
                    
                except Exception as e:
                    print(f"Error generating visualization: {e}")
                    # Fallback to regular visualization
                    try:
                        G = self.adf.visualiseNetwork(self.case)
                        filename = f"{self.caseName}.png"
                        G.write_png(filename)
                        print(f"Basic visualization saved as {filename}")
                        try:
                            abs_path = os.path.abspath(filename)
                            print(f"ADM_VISUALIZATION:{abs_path}")
                            sys.stdout.flush()
                        except Exception:
                            pass
                    except Exception as e2:
                        print(f"Error with fallback visualization: {e2}")
            else:
                filename = f"{self.adf.name}.png"
                # Visualize domain without case data, but still include sub-ADMs
                print(f"Visualizing domain: {self.adf.name}")
                try:
                    # Use the comprehensive visualization that includes sub-ADMs even without case data
                    graph = self.adf.visualiseNetworkWithSubADMs()
                    graph.write_png(filename)
                    print(f"Graph saved as: {filename}")
                    try:
                        abs_path = os.path.abspath(filename)
                        print(f"ADM_VISUALIZATION:{abs_path}")
                        sys.stdout.flush()
                    except Exception:
                        pass
                except Exception as e:
                    print(f"Error with sub-ADM visualization: {e}")
                    # Fallback to regular visualization
                    try:
                        graph = self.adf.visualiseNetwork()
                        graph.write_png(filename)
                        print(f"Basic visualization saved as: {filename}")
                        try:
                            abs_path = os.path.abspath(filename)
                            print(f"ADM_VISUALIZATION:{abs_path}")
                            sys.stdout.flush()
                        except Exception:
                            pass
                    except Exception as e2:
                        print(f"Error with fallback visualization: {e2}")
                        return
            
            # Try to open the image if possible
            try:
                if sys.platform.startswith('linux'):
                    os.system(f"xdg-open {shlex.quote(filename)}")
                elif sys.platform.startswith('darwin'):
                    os.system(f"open {shlex.quote(filename)}")
                elif sys.platform.startswith('win'):
                    os.system(f"start {shlex.quote(filename)}")
            except:
                print(f"Image saved as {filename}. Please open it manually.")
                
        except Exception as e:
            print(f"Error creating visualization: {e}")
    
    def visualize_domain_minimal(self):
        """Visualize the domain as a minimalist structure graph"""
        print("\n" + "="*50)
        print("Minimal Structure View")
        print("="*50)
        
        try:
            # Determine filename based on whether we have a case
            if self.caseName and self.case:
                filename = f"{self.caseName}_minimal.png"
                print(f"Generating minimal structure view with case data...")
                try:
                    # Use the minimalist visualization with case data
                    G = self.adf.visualiseNetworkMinimal(self.case)
                    
                    # Save the visualization
                    G.write_png(filename)
                    print(f"Minimal structure view saved as {filename}")
                    try:
                        abs_path = os.path.abspath(filename)
                        print(f"ADM_VISUALIZATION:{abs_path}")
                        sys.stdout.flush()
                    except Exception:
                        pass
                    
                except Exception as e:
                    print(f"Error generating minimal visualization: {e}")
                    return
            else:
                filename = f"{self.adf.name}_minimal.png"
                print(f"Generating minimal structure view for domain: {self.adf.name}")
                try:
                    # Use the minimalist visualization without case data
                    graph = self.adf.visualiseNetworkMinimal()
                    graph.write_png(filename)
                    print(f"Minimal structure view saved as: {filename}")
                    try:
                        abs_path = os.path.abspath(filename)
                        print(f"ADM_VISUALIZATION:{abs_path}")
                        sys.stdout.flush()
                    except Exception:
                        pass
                except Exception as e:
                    print(f"Error with minimal visualization: {e}")
                    return
            
            # Try to open the image if possible
            try:
                if sys.platform.startswith('linux'):
                    os.system(f"xdg-open {shlex.quote(filename)}")
                elif sys.platform.startswith('darwin'):
                    os.system(f"open {shlex.quote(filename)}")
                elif sys.platform.startswith('win'):
                    os.system(f"start {shlex.quote(filename)}")
            except:
                print(f"Image saved as {filename}. Please open it manually.")
                
        except Exception as e:
            print(f"Error creating minimal visualization: {e}")

def main():
    """Main function"""
    cli = CLI()
    
    try:
        cli.main_menu()
    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()  