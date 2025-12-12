"""
New CLI Experiment designed for interaction with LLMs

To Do:

    - Delete block comments
"""

import sys
import os
import argparse
from new_inventive_step_ADM import adm_initial, adm_main
import logging

logger = logging.getLogger("ADM_CLI_Tool")
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

class CLI():
    """
    """
    def __init__(self,adm):
        """
        
        """
        self.case = []
        self.adm = adm
        self.caseName = None
        #track which nodes have been evaluated so far
        self.evaluated_blfs = set()

    def query_domain(self):
        """Query the domain by answering questions"""
         
        #sets case name 
        if not self.caseName: 
            self.caseName = input("[QUESTION] Enter case name: ").strip()
            if self.caseName == '':
                print("No case name provided.")

        #get a copy of nodes and question order
        nodes = self.adm.nodes.copy()
        question_order = self.adm.questionOrder.copy() if self.adm.questionOrder else []

        #only proceeds if question order specified
        if question_order != []:
            while question_order:
                question_order, nodes = self.questiongen(question_order, nodes)
        
        else:
            raise ValueError("No question order specified")

        #process and display outcome
        self.show_outcome()
        
        print(f"Case: {self.case}")
        
        #add to launch next ADM more easily
        #return True if 

    def questiongen(self, question_order, nodes):
        """
        Generates questions based on the question order and current nodes
        """
        
        #early stop check
        if self.evaluated_blfs:
            self.adm.case = self.case
            logger.debug("arrived at self.evaluated questions")
            logger.debug(f'{self.adm.case}')
            if self.adm.check_early_stop(self.evaluated_blfs):
                # return empty list to stop recursion
                return [], nodes
        
        # to ensure the question gen procedure stops 
        if not question_order:
            return question_order, nodes
        
        #question under consideration
        current_question = question_order[0]
        
        #check if it is an information question           
        if current_question in self.adm.information_questions:
            
            #this is an information question
            question_text = self.adm.information_questions[current_question]
            answer = input(f"{question_text}: ").strip()
            
            self.adm.setFact(current_question, answer)
            
            #remove from question order and continue
            question_order.pop(0)
            return self.questiongen(question_order, nodes)
       
        #check if this is a question instantiator
        elif current_question in self.adm.question_instantiators:
            
            instantiator = self.adm.question_instantiators[current_question]
            if not self.gates_satisfied(instantiator, self.case):
                logger.debug(f"Skipping {current_question} - gates cannot be satisfied")
                self._mark_blfs_as_evaluated(instantiator)
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
            
            #process the question instantiator
            x = self.questionHelper(None, current_question)

            if x:
                self._mark_blfs_as_evaluated(instantiator)
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
            else:
                self._mark_blfs_as_evaluated(instantiator)
                # Any other return value means there's an issue, skip permanently
                logger.debug(f"Skipping {current_question} - processing failed")
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
        
        # Check if this is a regular node
        elif current_question in self.adm.nodes:
            current_node = self.adm.nodes[current_question]
            
            if not self.gates_satisfied(current_node, self.case):
                logger.debug(f"Skipping {current_question} - gates cannot be satisfied")
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
            
            # # Check if this is a SubADMBLF
            # elif hasattr(current_node, 'evaluateSubADMs'):
            #     return self.handleSubADMBLF(current_question, current_node, question_order, nodes)
            
            # # Check if this is an EvaluationBLF
            # elif hasattr(current_node, 'evaluateResults'):
            #     return self.handleEvaluationBLF(current_question, current_node, question_order, nodes)
            
            #process blf
            x = self.questionHelper(current_node, current_question)
            
            #mark as evaluated
            self.evaluated_blfs.add(current_question)
            if x:
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
            else:
                return question_order, nodes
        
        else:
            self.evaluated_blfs.add(current_question)
            question_order.pop(0)
            return self.questiongen(question_order, nodes)
    
    def _mark_blfs_as_evaluated(self, instantiator):
        """
        Helper to extract ALL possible BLFs from a question instantiator 
        and add them to the evaluated set.
        """
        mapping = instantiator.get('blf_mapping', {})
        for outcome in mapping.values():
            if isinstance(outcome, list):
                self.evaluated_blfs.update(outcome)
            elif isinstance(outcome, str) and outcome:
                self.evaluated_blfs.add(outcome)
           
    def gates_satisfied(self, candidate, case):
        """
        Checks and attempts to satisfy all gates for a node or instantiator.
        Returns True if all are satisfied, False otherwise.
        """
        #supports gated BLFs
        gating_nodes = []
        if hasattr(candidate, 'check_gated'):
            #it's a node with dependencies
            if candidate.check_gated(case):
                return True
            gating_nodes = getattr(candidate, 'gated_node', [])
        
        #supports Q instantiators
        elif isinstance(candidate, dict) and candidate.get('gating_node'):
            gating_nodes = candidate['gating_node']
            if isinstance(gating_nodes, str):
                gating_nodes = [gating_nodes]
        else:
            return True  # No dependencies

        #try to satisfy all dependencies
        for dep in gating_nodes:
            if dep not in case:
                if not self.evaluateGates(dep, None):
                    return False
        return True
            
    def evaluateGates(self, node, current_question):
        """Helper method to evaluate a gate node and add it to case if satisfied"""
        
        gating_node = self.adm.nodes[node]
                
        #check if gate node has acceptance conditions and can be evaluated
        if gating_node.acceptance:
            try:
                #ensure all child gates are evaluated (but don't require them to be satisfied)
                if gating_node.children:
                    logger.debug(f"{node} has children: {node.children}")
                    for child_name in gating_node.children:
                        if child_name not in self.case:
                            logger.debug(f"Evaluating child: {child_name}")
                            child_node = self.adm.nodes[child_name]
                            if child_node.acceptance:
                                # recursively evaluate this child (but don't require it to succeed)
                                self.evaluateGates(child_name, f"child of {node}")
                        else:
                            logger.debug(f"Child {child_name} has no acceptance conditions")
                
                #evaluate the gate node itself
                logger.debug(f"Children evaluated, now evaluating {node}")
                
                #temporarily set the case on the adm object for evaluation
                original_case = getattr(self.adm, 'case', None)
                self.adm.case = self.case.copy()
                
                evaluation_result = self.adm.evaluateNode(gating_node)

                #restore the original case on the adm object after evaluation
                if original_case is not None:
                    self.adm.case = original_case
                else:
                    delattr(self.adm, 'case')
                
                if evaluation_result:
                    #gate node can be satisfied, add it to case
                    if node not in self.case:
                        self.case.append(node)
                    
                    logger.debug(f"Gate {node} now satisfied for {current_question}")
                    return True
                else:
                    #gate node cannot be satisfied
                    logger.debug(f"Gate {node} cannot be satisfied for {current_question}")
                    return False
                    
            except Exception as e:
                #restore the original case on the adm object in case of error
                if original_case is not None:
                    self.adm.case = original_case
                else:
                    delattr(self.adm, 'case')
                logger.debug(f"Error evaluating gate {node} for {current_question}: {e}")
                return False
        else:
            # Gate node has no acceptance conditions, can't be evaluated
            logger.debug(f"Gate {node} has no acceptance conditions for {current_question}")
            return False
    
    def questionHelper(self, current_node, current_question):
        """
        Helper method to handle individual questions
        """
        
        #this is a question instantiator
        if current_node is None:
            instantiator = self.adm.question_instantiators[current_question]
            
            #note: gates are already checked in questiongen, so we can proceed directly
            
            #resolve any template variables in the question using facts
            question_text = instantiator['question']
            resolved_question = self.resolve_question_template(question_text)          
            
            print(f"\n{resolved_question}")
            
            #show available answers
            answers = list(instantiator['blf_mapping'].keys())
            for i, answer in enumerate(answers, 1):
                print(f"{i}. {answer}")
            
            #get user choice
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
            
            #instantiate the corresponding BLF(s)
            blf_names = instantiator['blf_mapping'][selected_answer]
            if isinstance(blf_names, str):
                blf_names = [blf_names]
            
            for blf_name in blf_names:
                #skip empty string BLFs - they're just placeholders
                if blf_name == "":
                    continue
                
                #add blf to case
                if blf_name not in self.case:
                    self.case.append(blf_name)
                else:
                    pass
                
                #ask factual ascription questions if configured
                if instantiator.get('factual_ascription') and blf_name in instantiator['factual_ascription']:
                    factual_questions = instantiator['factual_ascription'][blf_name]
                    for fact_name, question in factual_questions.items():
                        answer = input(f"{question}: ").strip()
                        if answer:
                            self.adm.setFact(fact_name, answer)
            
            return True
        
        #regular nodes
        else:
            
            if current_node.question:
                question_text = self.resolve_question_template(current_node.question)
                            
                #ask the question with retry loop
                while True:
                    answer = input(f"{question_text}\nAnswer (y/n): ").strip().lower()
                    
                    if answer in ['y', 'yes']:
                        if current_question not in self.case:
                            self.case.append(current_question)
                        return True
                    elif answer in ['n', 'no']:
                        return True
                    else:
                        print("Invalid answer, please answer y/n")
            else:
                if current_question not in self.case:
                    self.case.append(current_question)
                return True

    def resolve_question_template(self, question_text):
        """
        Resolves template variables in question text using collected facts
        """
        # Use the adm's template resolution method
        return self.adm.resolveQuestionTemplate(question_text)

    def show_outcome(self):
        """Show the evaluation outcome"""
        
        print("\n" + "="*50)
        print(f"Case Outcome: {self.caseName}")
        print("="*50)
        
        try:
            
            self.adm.temp_evaluated_nodes = set(self.evaluated_blfs)
            
            #returns the statements from the evaluated tree in a hierarchical structure
            reasoning = self.adm.evaluateTree(self.case)
            
            if not reasoning:
                print("No reasoning could be found.")
            else:
                print("Reasoning:")
                for depth, statement in reasoning:
                    #indent based on depth (2 spaces per level)
                    indent = "  " * depth
                    bullet = "└─ " if depth > 0 else ""
                    print(f"{indent}{bullet}{statement}")
                    
        except Exception as e:
            print(f"Error generating outcome: {e}")
        finally:
            #cleanup
            if hasattr(self.adm, 'temp_evaluated_nodes'):
                del self.adm.temp_evaluated_nodes
                 
    def visualize_domain(self,minimal=False):
        """
        Visualize the domain as a graph.
        Single source of truth: Calculates the filename and delegates to ADM.
        """
        print("\n" + "="*50)
        print("Visualize Domain")
        print("="*50)
        
        try:
            # 1. Determine Filename
            # Use case name if available, otherwise ADM name
            base_name = self.caseName if self.caseName else self.adm.name
            
            # Ensure we don't double-stack extensions (e.g., case.png.png)
            if not base_name.lower().endswith('.png'):
                filename = f"{base_name}.png"
            else:
                filename = base_name

            # 2. Determine Data Context
            # Only color the graph if we actually have case data
            case_data = self.adm.case
            print(case_data)

            print(f"Generating graph: {filename}")

            if minimal:
                # Minimalist Viz (Always useful for checking structure)
                self.adm.visualiseMinimalist(filename=f"{base_name}_structure.png")
            else:
                # 3. Generate & Save (One call only)
                self.adm.visualiseNetwork(filename=filename, case=case_data)
            
            # 4. Emit Path (for your environment integration)
            try:
                abs_path = os.path.abspath(filename)
                print(f"ADM_VISUALIZATION:{abs_path}")
                sys.stdout.flush()
            except Exception:
                pass
                
        except Exception as e:
            print(f"Error creating visualization: {e}")
            
def main():
    """Main function"""
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()

    # THE TOGGLE: If user flags --debug, switch level to DEBUG
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)        
        print("--- DEBUG MODE ENABLED ---")
        
    cli = CLI(adm=adm_initial())
    
    try:
        cli.query_domain()
        cli.visualize_domain(minimal=False)
    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()  