"""
Command line interface functionality for creating ADMs and can also interface with LLM

Last Updated: 15.12.2025

Status: Testing

Test Coverage: 57%
"""

import sys
import os
import argparse
from inventive_step_ADM import adm_initial, adm_main
import logging
from ADM_Construction import *
import json

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
                print("No case name provided.\n")

        #get a copy of nodes and question order
        nodes = self.adm.nodes.copy()
        question_order = self.adm.questionOrder.copy() if self.adm.questionOrder else []
        
        self.ask_questions(nodes,question_order)
        
        #evals root node - useful if you have multiple ordered adms 
        return True if self.adm.root_node.name in self.adm.case else False

    def ask_questions(self, nodes,question_order):
        #only proceeds if question order specified
        if question_order != []:
            while question_order:
                question_order, nodes = self.questiongen(question_order, nodes)
        
        else:
            raise ValueError("No question order specified")

        #process and display outcome
        self.show_outcome()
        
    def questiongen(self, question_order, nodes):
        """
        Generates questions based on the question order and current nodes
        """
        
        #early stop check
        if self.evaluated_blfs:
            self.adm.case = self.case
            logger.debug(f'Case: {self.adm.case}')
            if self.adm.check_early_stop(self.evaluated_blfs):
                # return empty list to stop recursion
                return [], nodes
            
        logger.debug('EARLY STOP ENDS ==========')
        
        # to ensure the question gen procedure stops 
        if not question_order:
            return question_order, nodes
        
        #question under consideration
        current_question = question_order[0]
        
        #check if it is an information question           
        if current_question in self.adm.information_questions:
            
            #this is an information question
            question_text = self.adm.information_questions[current_question]
            answer = input(f"[QUESTION] {question_text}: \n").strip()
            
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
                logger.debug(f"Skipping {current_question} - processing failed")
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
        
        #check if this is a regular node
        elif current_question in self.adm.nodes:
            current_node = self.adm.nodes[current_question]
            if not self.gates_satisfied(current_node, self.case):
                logger.debug(f"Skipping {current_question} - gates cannot be satisfied")
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
            
            #check if this is a SubADMNode
            elif isinstance(current_node, SubADMNode):
                logger.debug(f"recognised sub-adm node, {current_node}")

                sub_adm_result = current_node.evaluateSubADMs(ui_instance=self)
                
                if sub_adm_result:
                    #sub-ADM evaluation was successful, add to case
                    if current_question not in self.case:
                        self.case.append(current_question)
                    else:
                        pass
                    
                #mark as evaluated
                self.evaluated_blfs.add(current_question)

                #remove from question order and continue
                question_order.pop(0)
                
                return self.questiongen(question_order, nodes)
            
            #check if this is an EvaluationBLF
            elif isinstance(current_node, EvaluationNode):
                logger.debug(f"recognised evaluation node, {current_node}")
                    
                evaluation_result = current_node.evaluateResults(self.adm)
        
                if evaluation_result:
                    #evaluation was successful, add to case
                    if current_question not in self.case:
                        self.case.append(current_question)
                    else:
                        pass
                else:
                    #evaluation failed, don't add to case
                    pass
                
                #mark as evaluated
                self.evaluated_blfs.add(current_question)

                #remove from question order and continue
                question_order.pop(0)
                return self.questiongen(question_order, nodes)
                    
            else: 
                #process blf
                self.questionHelper(current_node, current_question)

                #mark as evaluated
                self.evaluated_blfs.add(current_question)

                question_order.pop(0)
                return self.questiongen(question_order, nodes)
                # else:
                #     return question_order, nodes
            
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
        
        logger.debug(f'{gating_nodes}, case: {case}')

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
                    logger.debug(f"{gating_node} has children: {gating_node.children}")
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
                
                logger.debug(self.adm.case)
                
                evaluation_result, _ = self.adm.evaluateNode(gating_node)

                logger.debug(evaluation_result)

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
            
            print(f"[QUESTION] \n{resolved_question}\n")
            
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
                        answer = input(f"[QUESTION] {question}: \n").strip()
                        self.adm.setFact(fact_name, answer)

            return
        
        #regular nodes
        else:
            
            if current_node.question:
                question_text = self.resolve_question_template(current_node.question)
                            
                #ask the question with retry loop
                while True:
                    answer = input(f"[QUESTION] {question_text}\nAnswer (y/n): ").strip().lower()
                    
                    if answer in ['y', 'yes']:
                        if current_question not in self.case:
                            self.case.append(current_question)
                        return 
                    elif answer in ['n', 'no']:
                        return
                    else:
                        print("Invalid answer, please answer y/n")
            else:
                if current_question not in self.case:
                    self.case.append(current_question)
                return 

    def resolve_question_template(self, question_text):
        """
        Resolves template variables in question text using collected facts
        """
        # Use the adm's template resolution method
        return self.adm.resolveQuestionTemplate(question_text)

    def show_outcome(self):
        """Show the evaluation outcome"""
        
        try:
            
            self.adm.evaluated_nodes = set(self.evaluated_blfs)
            
            logger.debug(f'eval nodes: {self.adm.evaluated_nodes}')
            
            #returns the statements from the evaluated tree in a hierarchical structure
            reasoning = self.adm.evaluateTree(self.case)
            
            print("\n" + "="*50)
            print(f"Case Outcome: {self.caseName}")
            print(f"Accepted factors: {self.case}")
            print("="*50)
            
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
                del self.adm.evaluated_nodes
                 
    def visualize_domain(self, minimal=False, name=None, visualize_sub_adms=True):
        """
        Visualize the domain as a graph, including optionally evaluated Sub-ADMs.
        Single source of truth: Calculates the filename and delegates to ADM.
        
        Parameters
        ----------
        minimal : bool
            If True, generates a minimalist structure graph.
        name : str, optional
            A prefix to add to the filename to distinguish graphs (e.g., "Initial", "Final").
        visualize_sub_adms : bool
            If True (default), scans for and visualizes any sub-ADM instances stored in facts.
        """
        print("\n" + "="*50)
        print("Visualize Domain")
        print("="*50)
        
        try:
            # 1. Determine Base Name
            # Use case name if available, otherwise ADM name
            raw_name = self.caseName if self.caseName else self.adm.name
            
            # Apply prefix if provided
            if name:
                base_name = f"{name}_{raw_name}"
            else:
                base_name = raw_name
            
            # 2. Handle Extensions
            # Ensure we don't double-stack extensions
            if not base_name.lower().endswith('.png'):
                filename = f"{base_name}.png"
            else:
                filename = base_name
                # Strip extension for folder creation later
                base_name = filename[:-4] 

            # 3. Determine Data Context
            # Only color the graph if we actually have case data
            case_data = self.adm.case
            print(f"Case Data: {case_data}")

            print(f"Generating graph: {filename}")

            if minimal:
                # Minimalist Viz (Always useful for checking structure)
                self.adm.visualiseMinimalist(filename=f"{base_name}_structure.png")
            else:
                # 4. Generate Main ADM (One call only)
                self.adm.visualiseNetwork(filename=filename, case=case_data)
                
                # 5. Generate Sub-ADMs (Iterate through facts to find stored instances)
                # Only proceed if the toggle is True and facts exist
                if visualize_sub_adms and hasattr(self.adm, 'facts'):
                    sub_dir = f"{base_name}_sub_adms"
                    dir_created = False
                    
                    for fact_key, fact_val in self.adm.facts.items():
                        # Check if this fact is a dictionary of sub-ADM instances
                        if fact_key.endswith('_sub_adm_instances') and isinstance(fact_val, dict):
                            
                            # Create directory only if we actually have sub-ADMs to show
                            if not dir_created:
                                if not os.path.exists(sub_dir):
                                    os.makedirs(sub_dir)
                                print(f"\n--- Visualising Sub-ADMs to '{sub_dir}/' ---")
                                dir_created = True
                            
                            # Extract node name from key (e.g., 'NodeName_sub_adm_instances')
                            node_name = fact_key.replace('_sub_adm_instances', '')
                            print(f"Processing Sub-ADMs for: {node_name}")
                            
                            for item_name, sub_adm_inst in fact_val.items():
                                # Create safe filename
                                safe_item = str(item_name).replace(" ", "_").replace("/", "-").replace("\\", "-")
                                sub_filename = os.path.join(sub_dir, f"{node_name}_{safe_item}.png")
                                
                                try:
                                    # Visualize the specific sub-ADM instance using its own case data
                                    sub_adm_inst.visualiseNetwork(filename=sub_filename, case=sub_adm_inst.case)
                                except Exception as e:
                                    print(f"  Error visualizing sub-ADM item '{item_name}': {e}")
            
            # 6. Emit Path (for your environment integration)
            try:
                abs_path = os.path.abspath(filename)
                print(f"ADM_VISUALIZATION:{abs_path}")
                sys.stdout.flush()
            except Exception:
                pass
                
        except Exception as e:
            print(f"Error creating visualization: {e}")

    def save_adm(self, folder_base="./Eval_Cases", name=None):
        """
        Saves the case, reasoning statements, evaluated nodes, and any sub-ADM results to a sub-folder named after the case.
        """
        # Use case name or ADM name for folder
        folder_name = self.caseName if self.caseName else self.adm.name
        save_dir = os.path.join(folder_base, folder_name)
        os.makedirs(save_dir, exist_ok=True)

        # Gather main ADM data
        case_data = {
            "case": self.case,
            "evaluated_nodes": list(self.evaluated_blfs),
        }

        # Get reasoning statements for main ADM
        try:
            self.adm.evaluated_nodes = set(self.evaluated_blfs)
            reasoning = self.adm.evaluateTree(self.case)
            case_data["reasoning"] = [
                {"depth": depth, "statement": statement} for depth, statement in (reasoning or [])
            ]
        except Exception as e:
            case_data["reasoning"] = [f"Error generating reasoning: {e}"]

        # Save main ADM as JSON
        json_path = os.path.join(save_dir, f"adm_{name}_summary.json")
        with open(json_path, "w") as f:
            json.dump(case_data, f, indent=2)
        print(f"ADM summary saved to: {json_path}")

        # --- Save sub-ADM results if present ---
        if hasattr(self.adm, "facts"):
            for fact_key, fact_val in self.adm.facts.items():
                if fact_key.endswith('_sub_adm_instances') and isinstance(fact_val, dict):
                    sub_dir = os.path.join(save_dir, f"{fact_key}")
                    os.makedirs(sub_dir, exist_ok=True)
                    for item_name, sub_adm_inst in fact_val.items():
                        sub_case_data = {
                            "case": getattr(sub_adm_inst, "case", []),
                            "evaluated_nodes": list(getattr(sub_adm_inst, "case", [])),  # fallback if no evaluated_blfs
                        }
                        # Try to get reasoning for sub-ADM
                        try:
                            sub_reasoning = sub_adm_inst.evaluateTree(sub_case_data["case"])
                            sub_case_data["reasoning"] = [
                                {"depth": depth, "statement": statement} for depth, statement in (sub_reasoning or [])
                            ]
                        except Exception as e:
                            sub_case_data["reasoning"] = [f"Error generating reasoning: {e}"]
                        # Save sub-ADM as JSON
                        safe_item = str(item_name).replace(" ", "_").replace("/", "-").replace("\\", "-")
                        sub_json_path = os.path.join(sub_dir, f"{safe_item}_summary.json")
                        with open(sub_json_path, "w") as f:
                            json.dump(sub_case_data, f, indent=2)
                        print(f"Sub-ADM summary saved to: {sub_json_path}")
        
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
        result = cli.query_domain()
        cli.save_adm(name='initial')  # Save initial ADM

        
        if result:   
            logger.debug('Moving to main ADM')     
            cli_2 = CLI(adm=adm_main())
            cli_2.caseName = cli.caseName
            cli_2.adm.facts = cli.adm.facts
            
            _ = cli_2.query_domain()  
            cli_2.save_adm(name='main')  # Save main ADM
      
        
        #cli.visualize_domain(minimal=False,name="Initial",visualize_sub_adms=False)
        #cli_2.visualize_domain(minimal=False,name="Main")

    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()  