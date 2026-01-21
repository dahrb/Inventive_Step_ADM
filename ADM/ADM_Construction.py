"""
Creates the classes used to instantiate the Inventive Step ADM and core traversal functionalities

Last Updated: 15.12.2025

Status: Testing 

Test Coverage: 86%

"""

from pythonds import Stack
import pydot
import re
import logging
import os

logger = logging.getLogger(__name__)

class ADM:
    """
    A class used to represent the ADM graph

    Attributes
    ----------
    name : str
        the name of the ADM
    nodes : dict
        the nodes which constitute the ADM
    reject : bool, default False
        is set to true when the reject keyword is used which lets the software know to reject the node rather than accep it when the condition is true
    nonLeaf : dict
        the nodes which are non-leaf that have children
    questionOrder : list
        an ordered list which determines which order the questions are asked in
    question : str, optional
        if the node is a base-level factor this stores the question
    statements : list
        the statements to be shown if the node is accepted or rejected
    nodeDone : list
        nodes which have been evaluated
    case : list
        the list of factors forming the case    
    
    Methods
    -------
    addNodes(name, acceptance = None, statement=None, question=None)
        allows nodes to be added to the adm from the Node() class
    addMulti(name, acceptance, statement, question)
        allows nodes to be added to the adm from the MultiChoice() class
    nonLeafGen()
        determines what is a non-leaf factor
    evaluateTree(case)
        evaluates the adm for a specified case
    evaluateNode(node)
        evaluates the acceptance conditions of the node
    postfixEvaluation(acceptance)
        evaluates the individual acceptance conditions which are in postfix notation
    checkCondition(operator, op1, op2 = None):
        checks the logical conditions for the acceptance condition, returning a boolean
    checkNonLeaf(node)
        checks if a node has children which need to be evaluated before it is evaluated
    questionAssignment()
        checks if any node requires a question to be assigned
    visualiseNetwork(case=None)
        allows visualisation of the ADM
    saveNew(name)
        allows the ADM to be saved as a .xlsx file
    saveHelper(wb,name)
        helper class for saveNew which provides core functionality
    """
    
    def __init__(self, name):
        """
        Parameters
        ----------
        name : str
            the name of the ADM
        """
        
        logger.info('ADM created')
      
        self.name = name
        #dictionary of nodes --> 'name': 'node object
        self.nodes = {}

        #initialise reject flag as False
        self.reject = False
        
        #dictionary of nodes which have children
        self.nonLeaf = {}
        self.questionOrder = []
        self.question_instantiators = {}
        self.information_questions = {}
        
        self.case = []
    
    def __str__(self):
        return self.name
     
    def addNodes(self, name, acceptance = None, statement=None, question=None,root=False):
        """
        adds nodes to ADM
        
        Parameters
        ----------
        name : str
            the name of the node
        acceptance : list
            a list of the acceptance conditions each of which should be a string
        statement : list
            a list of the statements which will be shown if a condition is accepted or rejected
        question : str
            the question to determine whether a node is absent or present
        """
        
        #create node instance
        node = Node(name, acceptance, statement, question)
        
        self.nodes[name] = node
        
        if root:
            self.root_node = node
            
        #creates children nodes for new node
        if node.children != None:
            for childName in node.children:
                if childName not in self.nodes:
                    node = Node(childName)
                    self.nodes[childName] = node
        
    def addQuestionInstantiator(self, question, blf_mapping, factual_ascription=None, question_order_name=None, gating_node=None):
        """
        Adds a question that can instantiate BLFs without creating an additional node in the model for the question i.e. this is used
        when you want to have a question with multiple choices and some of those choices instantiate BLFs
        
        Parameters
        ----------
        question : str
            the question text to ask the user
        blf_mapping : dict
            dictionary mapping answer choices to BLF names (or lists of BLF names) to instantiate
        factual_ascription : dict, optional
            dictionary mapping BLF names to additional factual questions to ask
        question_order_name : str, optional
            name to use in question order (if None, will be auto-generated)
        gating_node : str, optional
            the name of the node that if not satisfied prior to this question arising, will not trigger the question
        """
        
        #create a unique name for this question if not provided
        if question_order_name is None:
            question_order_name = f"question_{len(self.questionOrder) + 1}"
        
        self.question_instantiators[question_order_name] = {
            'question': question,
            'blf_mapping': blf_mapping,
            'factual_ascription': factual_ascription,
            'gating_node': gating_node 
        }
        
        #add the question to the question order
        if question_order_name not in self.questionOrder:
            self.questionOrder.append(question_order_name)

    def addSubADMNode(self, name, sub_adm, function, rejection_condition=False, check_node = []):
        """
        Adds a node that depends on evaluating a sub-ADM for each item i.e. the linking node between the main ADM and the Sub-ADM
        
        Parameters
        ----------
        name : str
            the name of the node to be instantiated
        sub_adm_creator : function
            function that creates and returns a sub-ADM instance
        function : str or function
            the function that returns the list of items to evaluate, or a list of items
        """
        
        #creates a node that handles sub-ADM evaluation
        node = SubADMNode(name, sub_adm, function, rejection_condition, check_node)
        self.nodes[name] = node
        
        #add to question order
        if name not in self.questionOrder:
            self.questionOrder.append(name)
    
    def addEvaluationNode(self, name, source_blf, target_node, statements=None, rejection_condition=False):
        """
        Adds a BLF that automatically evaluates based on sub-ADM results from another BLF. This enables us to query the sub-ADMs looking for
        whether a named target node has been accepted or not across the iterations.
        
        Parameters
        ----------
        name : str
            the name of the BLF to be instantiated
        source_blf : str
            the name of the BLF that contains the sub-ADM results to evaluate
        target_node : str
            the node name to look for in the sub-ADM cases (e.g., 'POSITIVE_RESOURCE')
        statements : list, optional
            statements to show if the BLF is accepted or rejected
        """
        
        #create a special node that handles result evaluation
        node = EvaluationNode(name, source_blf, target_node, statements, rejection_condition)
        self.nodes[name] = node
        
        #add to question order
        if name not in self.questionOrder:
            self.questionOrder.append(name)

    def nonLeafGen(self):
        """
        determines which of the nodes is non-leaf i.e. a node with children     
        """
        
        #sets it back to an empty dictionary
        self.nonLeaf = {}
        
        #checks each node and determines if it is a non-leaf node (one with children)
        for name,node in zip(self.nodes,self.nodes.values()):
            
            #adds node to dict of nodes with children
            if node.children != None and node.children != []:
                self.nonLeaf[name] = node
            #also include EvaluationBLF nodes even if they don't explicitly have children as they do not use a question to instantiate them
            elif hasattr(node, 'evaluateResults'):
                self.nonLeaf[name] = node
            else:
                pass
            
    def checkNonLeaf(self, node):
        """
        checks if a given node has children which need to be evaluated before it can be evaluated
        
        Parameters
        ----------
        node : class
            the node class to be evaluated
        
        """
        
        #checks if all children of a nonleaf node have been evaluated
        #returns False if at least 1 has not; otherwise returns True
        for node in node.children:
    
            if node in self.nonLeaf:
                
                if node in self.node_done:
                    pass
                
                else:
                    return False

            else:
                pass

        return True

    def check_early_stop(self, evaluated_nodes):
        """
        determines if the ADM can be fully evaluated earlier than all blfs being asked
        
        Parameters
        ----------
        node : class
            the node class to be evaluated
        """
        logger.debug('EARLY STOP BEGINS ========')
        if not hasattr(self, 'root_node'):
            return False
        
        self.evaluated_nodes = set(evaluated_nodes)
        logger.debug(f"{self.evaluated_nodes}")
        
        #try to accept non-leaf nodes that can be accepted - accounts for complexities with reject conditions
        self.nonLeafGen()
        for name, node in self.nonLeaf.items():
            # Evaluate node in 3vl mode
            val, idx = self.evaluateNode(node, mode='3vl')
            if val is True:
                # Check for reject conditions in the acceptance logic
                has_unknown_reject = False
                if node.acceptance:
                    # For each acceptance condition, check if it contains 'reject'
                    for i, acc in enumerate(node.acceptance):
                        if 'reject' in acc:
                            # Evaluate this acceptance condition directly
                            self.reject = False
                            eval_result = self.postfixEvaluation(acc, mode='3vl')
                            # If the result is None (unknown), we cannot accept early
                            if eval_result is None:
                                has_unknown_reject = True
                                break
                if not has_unknown_reject and name not in self.case:
                    self.case.append(name)
        try:
            #use 3vl mode - can return T/F/Unknown - Unknown is for unevaluated blfs
            result,_ = self.evaluateNode(self.root_node, mode='3vl')

            logger.debug(f'result early stop = {result}')
            
            if result is not None:
                status = "ACCEPTED" if result else "REJECTED"
                print(f"[Early Stop] {self.root_node.name} is {status}.")
                return True
            return False
        
        except:
            raise ValueError('can\'t evaluate early stopping')
                
    def evaluateTree(self, case):
        """
        Evaluates the adm for a given case.
        """
        self.statements = []
        self.node_done = []
        self.case = case
        
        self.nonLeafGen()
        
        non_leaf_nodes = self.nonLeaf.copy()
        
        while non_leaf_nodes != {}:
            current_batch = list(zip(list(non_leaf_nodes.keys()), list(non_leaf_nodes.values())))
            
            for name, node in current_batch:
                
                # 1. Evaluate Nodes (Special)
                if hasattr(node, 'evaluateResults'):
                    self.node_done.append(name)
                    if node.evaluateResults(self):
                        if name not in self.case: self.case.append(name)
                    non_leaf_nodes.pop(name)
                
                # 2. Standard Logic Nodes
                elif self.checkNonLeaf(node):
                    self.node_done.append(name)
                    
                    # --- GUARD: Check if acceptance logic exists ---
                    if node.acceptance:
                        val,_ = self.evaluateNode(node)
                        if val:
                            if name not in self.case: self.case.append(name)
                    else:
                        # No logic? Truth is "Is it in the case?"
                        # (Usually these are leaves, but could be special nodes)
                        pass 
                    
                    non_leaf_nodes.pop(name)
        
        self.case = list(set(self.case))
        
        logger.debug('GENERATE EXPLANATION')
        self.statements = self._generate_explanation()
        
        logger.debug(f'statements {self.statements}')
        
        return self.statements

    def _generate_explanation(self):
        """
        Generates explanation trace. 
        Guards against calling evaluateNode on nodes with no logic.
        """
        statements_with_depth = []
        visited_nodes = set() 
        
        def traverse(node, depth):
            if node.name in visited_nodes:
                return
            
            # --- GUARD: Only call evaluateNode if acceptance logic exists ---
            if not node.acceptance:
                # Fallback: Status is determined by presence in Case
                status = node.name in self.case
                index = -1
                logger.debug(f'REASONING GEN [No Logic] - {node.name}, {status}')
            else:
                # Normal Logic Evaluation
                status, index = self.evaluateNode(node, mode='standard')
                logger.debug(f'REASONING GEN - {node.name}, {status}, {index}')
            
            # Treat None as False
            if status is None:
                status = False

            visited_nodes.add(node.name)
            
            # Statement Selection
            stmt = None
            if node.statement:
                if status is True:
                    if index != -1 and index < len(node.statement):
                        stmt = node.statement[index]
                    else:
                        # Default to first statement if index not applicable
                        stmt = node.statement[0] if len(node.statement) > 0 else None
                elif status is False:
                    if self.reject and index != -1 and index < len(node.statement):
                         stmt = node.statement[index]
                    else:
                         stmt = node.statement[-1] if len(node.statement) > 0 else None
            
            if stmt:
                statements_with_depth.append((depth, stmt))
            
            if node.children:
                for child_name in node.children:
                    if child_name in self.nodes:
                        traverse(self.nodes[child_name], depth + 1)

        if hasattr(self, 'root_node'):
            traverse(self.nodes[self.root_node.name], 0)
            
        return statements_with_depth
    
    # def evaluateNode(self, node, mode='standard'):
    #     """
    #     Evaluates a node's acceptance conditions with Asymmetric 3VL Safety.
    #     """   
    #     logger.debug(f"--- EVAL NODE: {node.name} (Mode: {mode}) ---")

    #     # --- 3VL LEAF HANDLING ---
    #     if mode == '3vl' and not node.children:
    #         if node.name in self.case:
    #             logger.debug(f"  [Leaf] {node.name} is TRUE (Found in case)")
    #             return True, 0
    #         elif hasattr(self, 'evaluated_nodes') and node.name in self.evaluated_nodes:
    #             logger.debug(f"  [Leaf] {node.name} is FALSE (Evaluated, not in case)")
    #             return False, -1
    #         else:
    #             logger.debug(f"  [Leaf] {node.name} is UNKNOWN (Not yet evaluated)")
    #             return None, -1

    #     # --- ASYMMETRIC EVALUATION ---
    #     has_unknown_reject = False    # Tracks if we have an unchecked "Defeater"
    #     has_unknown_positive = False  # Tracks if we have an unchecked "Enabler"
    #     successful_accept_index = -1  # Stores the index of a valid positive path
    #     definitive_reject_index = -1  # Stores index of a definite reject path (found True && reject)
        
    #     for index, condition in enumerate(node.acceptance):
            
    #         logger.debug(f"  [Iter {index}] Testing: '{condition}'")
    #         self.reject = False
            
    #         # Evaluate the single condition
    #         result = self.postfixEvaluation(condition, mode=mode)
            
    #         print('accept = ',condition)
    #         print('result = ', result)
            
    #         # --- 1. DEFINITIVE REJECTION (record, but do not decide yet) ---
    #         if result is True and self.reject:
    #             logger.debug(f"  [Iter {index}] -> DEFINITIVE REJECT PATH (Reject flag set on True condition) — recorded")
    #             definitive_reject_index = index
    #             # Do not return immediately: there may be Unknown positive paths that require deferring decision
    #             continue

    #         # --- 2. POTENTIAL ACCEPTANCE (Defer Decision) ---
    #         elif result is True and not self.reject:
    #             logger.debug(f"  [Iter {index}] -> Positive Path Found (Deferring to check for Unknown Rejects)")
    #             successful_accept_index = index
    #             # We do NOT return True yet. We must ensure no 'reject' conditions were skipped as Unknown.
    #             continue

    #         # --- 3. CONDITION FALSE (Ignore) ---
    #         elif result is False:
    #             logger.debug(f"  [Iter {index}] -> Condition Failed")
    #             continue

    #         # --- 4. UNKNOWN RESULT ---
    #         elif result is None:
    #             # Heuristic: Is this a "Reject" condition?
    #             tokens = condition.split()
    #             if 'reject' in tokens:
    #                 logger.debug(f"  [Iter {index}] -> Unknown Reject Condition (Marking Safety Risk)")
    #                 has_unknown_reject = True
    #             else:
    #                 logger.debug(f"  [Iter {index}] -> Unknown Positive Condition")
    #                 has_unknown_positive = True
                    
    #     print('reject ind: ',definitive_reject_index)
    #     print('positive ind: ',successful_accept_index)
            

    #     # --- FINAL DECISION LOGIC ---

    #     # Scenario A: We found a Valid Positive Path
    #     if successful_accept_index != -1:
    #         if has_unknown_reject:
    #             logger.debug(f"  -> FINAL: UNKNOWN (Valid positive path exists, but blocked by Unknown Reject)")
    #             return None, -1
    #         else:
    #             logger.debug(f"  -> FINAL: ACCEPTED (Index {successful_accept_index})")
    #             return True, successful_accept_index

    #     # Scenario B: No valid positive path found
    #     # If a definitive reject path was found, honour it only if there are no unknown positive paths
    #     if definitive_reject_index != -1:
    #         if has_unknown_positive:
    #             logger.debug(f"  -> FINAL: UNKNOWN (Definitive reject exists but some positive paths are Unknown)")
    #             return None, -1
    #         else:
    #             logger.debug(f"  -> FINAL: FALSE (Definitive reject path found at index {definitive_reject_index})")
    #             return False, definitive_reject_index

    #     # Scenario C: No definitive reject and no positive path
    #     if has_unknown_positive:
    #         logger.debug(f"  -> FINAL: UNKNOWN (No positive path yet, but some are Unknown)")
    #         return None, -1
    #     else:
    #         logger.debug(f"  -> FINAL: FALSE (No possible acceptance path)")
    #         return False, -1
    
    # def evaluateNode(self, node, mode='standard'):
    #     """
    #     Evaluates a node's acceptance conditions with Asymmetric 3VL Safety.
    #     """   
    #     logger.debug(f"--- EVAL NODE: {node.name} (Mode: {mode}) ---")

    #     #3VL BLF handling 
    #     if mode == '3vl' and not node.children:
    #         if node.name in self.case:
    #             logger.debug(f"{node.name} is TRUE (BLF in case)")
    #             return True, 0
    #         elif hasattr(self, 'evaluated_nodes') and node.name in self.evaluated_nodes:
    #             logger.debug(f"{node.name} is FALSE (BLF not in case)")
    #             return False, -1
    #         else:
    #             logger.debug(f"{node.name} is UNKNOWN (BLF not evaluated)")
    #             return None, -1

    #     #Full 3vl evaluation
    #     has_unknown_reject = False    # Tracks if we have an unchecked "Defeater"
    #     has_unknown_positive = False  # Tracks if we have an unchecked "Enabler"
    #     successful_accept_index = -1  # Stores the index of a valid positive path
        
    #     #['DocumentaryEvidence','reject Contested','accept'],
        
    #     for index, condition in enumerate(node.acceptance):
            
    #         logger.debug(f"  [Iter {index}] Testing: '{condition}'")
            
    #         #resets reject condition
    #         self.reject = False
            
    #         #evaluates the condition with postfix
    #         result = self.postfixEvaluation(condition, mode=mode)
            
    #         #1. Node has been accepted and is a reject condition
    #         # - in this case we can 
    #         if result is True and self.reject:
    #             logger.debug(f"Rejected due to {condition}")
    #             return False, index 
            
    #         #2. Node has been accepted and there is NO reject in the condition
    #         # - don't return True yet though because 
    #         elif result is True and not self.reject:
    #             logger.debug(f"Potential for accept due to {condition}")
    #             #successful_accept_index = index
    #             return True, index 

    #             # We do NOT return True yet. We must ensure no 'reject' conditions were skipped as Unknown.
                
    #         # --- 3. CONDITION FALSE (Ignore) ---
    #         elif result is False:
    #             logger.debug(f"Condition rejected due to {condition}")
    #             continue
                
    #         # --- 4. UNKNOWN RESULT ---
    #         elif result is None:
     
    #             if self.reject:
    #                 logger.debug(f"Unknown reject condition due to {condition}")
    #                 has_unknown_reject = True
    #             else:
    #                 logger.debug(f"Unknown positive condition due to {condition}")
    #                 has_unknown_positive = True

        
    #     #Final Decision section
                
    #     # Scenario A: We found a Valid Positive Path
    #     if successful_accept_index != -1:
    #         if has_unknown_reject:
    #             # We want to accept, but a Reject Condition is Unknown.
    #             # We CANNOT Accept safely.
    #             logger.debug(f"  -> FINAL: UNKNOWN (Valid positive path exists, but blocked by Unknown Reject)")
    #             return None, -1
    #         else:
    #             # We have a positive path and NO unknown reject risks.
    #             logger.debug(f"  -> FINAL: ACCEPTED (Index {successful_accept_index})")
    #             return True, successful_accept_index

    #     # Scenario B: No Valid Positive Path found (All evaluated were False or Unknown)
    #     else:
    #         if has_unknown_positive:
    #             # We might find a positive path later.
    #             logger.debug(f"  -> FINAL: UNKNOWN (No positive path yet, but some are Unknown)")
    #             return None, -1
    #         else:
    #             # All positive paths are definitely False.
    #             # It doesn't matter if we have Unknown Rejects (has_unknown_reject), 
    #             # because we can't Accept anyway.
    #             logger.debug(f"  -> FINAL: FALSE (No possible acceptance path)")
    #             return False, -1
    
    def evaluateNode(self, node, mode='standard'):
        """
        Evaluates a node's acceptance conditions with Asymmetric 3VL Safety.
        
        Logic:
        1. Iterate through conditions.
        2. If a condition is TRUE:
           - If it triggers REJECT: Return FALSE immediately (Short-circuit).
           - If it triggers ACCEPT: Return TRUE immediately (Short-circuit).
        3. If a condition is UNKNOWN:
           - Differentiate between Unknown Positive (Enabler) and Unknown Negative (Defeater).
           - Continue searching for a definitive True.
        4. End of Loop:
           - If no True condition found:
             - If we had Unknown Enablers (Positive): Return UNKNOWN.
             - If we only had Unknown Defeaters (Reject) but all Enablers were False: Return FALSE.
               (Rationale: Even if the defeater doesn't fire, there is no Enabler to accept the node).
        """   
        logger.debug(f"--- EVAL NODE: {node.name} (Mode: {mode}) ---")

        #3VL Leaf handling
        if mode == '3vl' and not node.children:
            if node.name in self.case:
                logger.debug(f"{node.name} is TRUE (BLF in case)")
                return True, 0
            elif hasattr(self, 'evaluated_nodes') and node.name in self.evaluated_nodes:
                logger.debug(f"{node.name} is FALSE (BLF not in case)")
                return False, -1
            else:
                logger.debug(f"{node.name} is UNKNOWN (BLF not evaluated)")
                return None, -1

        has_unknown = False 
        
        #check conditions
        for index, condition in enumerate(node.acceptance):
            
            logger.debug(f"  [Iter {index}] Testing: '{condition}'")
            
            #reset reject flag
            self.reject = False
            
            #eval condition
            result = self.postfixEvaluation(condition, mode=mode)

            if result is True:
                
                if has_unknown and self.reject:
                    return False, index
                
                elif has_unknown and not self.reject:
                    return None, -1                
                
                if self.reject:
                    logger.debug(f"Rejected due to {condition}")
                    return False, index 
                
                else:
                    logger.debug(f"Accepted due to {condition}")
                    
                    return True, index 
            
            elif result is False:
                
                continue 
                
            elif result is None:
                logger.debug(f"Unknown result for condition: {condition}")
                
                #We check if this condition contains 'reject'?
                #if YES: it is a defeater and if we have no valid pathway to accept i.e. all other conditions are reject then we can never accept this node.
                #if NO: we can safely return as unknown since we need to evaluate that node before going any further.
                if 'reject' in condition:
                    has_unknown = True
                else:
                    return None, -1
        
        return False, -1

            
    def postfixEvaluation(self, acceptance, mode='standard'):
        """
        Evaluates a postfix string with stack tracing logs.
        """
        # logger.debug(f"    [Postfix] Eval: '{acceptance}'") 
        operandStack = Stack()
        tokenList = acceptance.split()
        
        for token in tokenList:
            
            if token == 'accept':
                operandStack.push(True)
            
            elif token == 'reject':
                val = operandStack.pop()
                if val is True:
                    self.reject = True
                    # logger.debug(f"      [Op: Reject] Triggered! (Input was True)")
                operandStack.push(val)
                
            elif token == 'not':
                op1 = operandStack.pop()
                res = self.checkCondition('not', op1, mode=mode)
                operandStack.push(res)
                
            elif token in ['and', 'or']:
                op2 = operandStack.pop()
                op1 = operandStack.pop()
                res = self.checkCondition(token, op1, op2, mode=mode)
                operandStack.push(res)
            
            else:
                # Resolve Term
                val, _ = self._resolve_term(token, mode)
                operandStack.push(val)
        
        if operandStack.isEmpty():
            return False
            
        final_res = operandStack.pop()
        # logger.debug(f"    [Postfix] Returns: {final_res}")
        return final_res

    def _resolve_term(self, term, mode):
        """
        Helper to resolve a term to a value.
        """
        if term in self.nodes:
            if mode == 'standard':
                val = term in self.case
                return val, 0
            
            elif mode == '3vl':
                # 1. Definitely True
                if term in self.case:
                    return True, 0
                
                # 2. Definitely False (if using evaluated_nodes tracking)
                if hasattr(self, 'evaluated_nodes') and term in self.evaluated_nodes:
                    return False, -1
                
                # 3. Recursive Check
                val, idx = self.evaluateNode(self.nodes[term], mode='3vl')
                return val, idx
                
        #default (Term not found or external fact not in case)
        return False, -1

    def checkCondition(self, operator, v1, v2=None, mode='standard'):
        """
        Strict 3-Valued Logic (Kleene) Truth Table.
        Inputs v1, v2 are guaranteed to be True, False, or None.
        """
        # --- OR Logic ---
        if operator == "or":
            if v1 is True or v2 is True:
                return True
            if v1 is None or v2 is None:
                return None
            return False
        
        # --- AND Logic ---
        elif operator == "and":
            if v1 is False or v2 is False:
                return False
            if v1 is None or v2 is None:
                return None
            return True
        
        # --- NOT Logic ---
        elif operator == "not":
            if v1 is None:
                return None
            return not v1
            
        return False
    
    def addGatedBLF(self, name, gated_node, question_template):
        """
        Adds a BLF that depends on another node
        
        Parameters
        ----------
        name : str
            the name of the BLF
        gated_node : str
            the name of the node this BLF depends on
        question_template : str
            the question template that can reference inherited factual ascriptions
        statements : list
            the statements to show if the BLF is accepted or rejected
        """
        
        #create a node that tracks dependencies
        node = GatedBLF(name, gated_node, question_template)
        self.nodes[name] = node
        
        # Add to question order
        if name not in self.questionOrder:
            self.questionOrder.append(name)
            
    def visualiseNetwork(self, filename=None, case=None):
        """
        Generates a hierarchical visualization of the ADM.
        Adds '+' (Support) or '-' (Attack) labels to edges based on logic.
        """
        
        # 1. Initialize Directed Graph
        graph = pydot.Dot(self.name, graph_type='digraph', rankdir='TB')
        
        # Global styles
        graph.set_node_defaults(style="filled", fontname="Arial")
        graph.set_edge_defaults(color="#333333", arrowhead="vee", fontsize="12")

        # 2. Determine Node Colors
        node_colors = {}
        if case is not None:
            for node_name in self.nodes:
                if node_name in case:
                    node_colors[node_name] = "#90EE90"  # Light Green
                else:
                    node_colors[node_name] = "#FFB6C1"  # Light Red
        else:
            for node_name in self.nodes:
                node_colors[node_name] = "white"

        # 3. Create Nodes and Edges
        issue_nodes = []
        if hasattr(self, 'root_node') and self.root_node.children:
            issue_nodes = self.root_node.children

        for name, node in self.nodes.items():
            
            # -- Shape Logic --
            shape = "box"
            peripheries = "1"
            
            if hasattr(self, 'root_node') and name == self.root_node.name:
                shape = "doubleoctagon"
                peripheries = '2'
            elif type(node).__name__ == 'SubADMNode':
                shape = "component" 
            elif type(node).__name__ == 'EvaluationNode':
                shape = "box"
                peripheries = "2"
            elif name in issue_nodes:
                shape = "ellipse" 
                peripheries = "2"
             
            elif node.children: 
                shape = "ellipse"
            else: 
                shape = "box"

            # Create Node
            pydot_node = pydot.Node(
                name, 
                label=name.replace("_", "\n"), 
                shape=shape,
                peripheries=peripheries,
                fillcolor=node_colors.get(name, "white"),
                color="black"
            )
            graph.add_node(pydot_node)

            # -- Edge Logic with +/- Labels --
            if node.children:
                for child in node.children:
                    
                    # Default to Supporting (+)
                    edge_label = "+"
                    
                    # Scan parent's acceptance conditions to see how the child is used
                    if node.acceptance:
                        for condition in node.acceptance:
                            tokens = condition.split()
                            if child in tokens:
                                # If the child contributes to a 'reject' or 'not' condition, it is Attacking (-)
                                if 'reject' in tokens or 'not' in tokens:
                                    edge_label = "-"
                                    break
                    
                    # Create Edge
                    edge = pydot.Edge(name, child, label=edge_label)
                    graph.add_edge(edge)

        # 4. Save Output
        out_name = filename if filename else f"{self.name}_hierarchy.png"
        
        try:
            graph.write_png(out_name)
            print(f"Graph generated successfully: {out_name}")
                    
        except Exception as e:
            print(f"Could not generate graph. Ensure Graphviz is installed.\nError: {e}")
            
    def visualiseMinimalist(self, filename=None):
        """
        Generates a publication-quality minimalist visualization (dots only).
        Constrained to a Portrait layout (Height > Width), scaling down if needed.
        """
        
        # 1. Initialize Graph
        graph = pydot.Dot(self.name, graph_type='digraph', rankdir='TB')
        
        # Global Styles for "Publication Quality"
        graph.set_graph_defaults(
            dpi="300",              
            bgcolor="white",
            splines="line",       
            nodesep="0.4",          
            ranksep="0.8",
            
            # --- PORTRAIT CONSTRAINTS ---
            # "8,12" defines a bounding box of 8x12 inches.
            # Graphviz will scale the graph DOWN to fit this box if necessary,
            # maintaining the aspect ratio.
            size="8,12",
            ratio="fill"  # Forces the graph to fill the dimensions (optional, usually 'auto' is safer to avoid distortion, but 'fill' enforces the rect)
        )
        
        # If 'fill' distorts too much, change ratio to "auto" 
        # and rely on 'size' to handle the boundaries.
        
        graph.set_node_defaults(
            label="",               
            shape="circle",         
            style="filled",
            fixedsize="true",       
            width="0.3",            
            penwidth="0"            
        )
        
        graph.set_edge_defaults(
            color="#555555",        
            penwidth="0.8",         
            arrowsize="0.6"         
        )

        # 2. Identify Node Types
        issue_nodes = []
        if hasattr(self, 'root_node') and self.root_node.children:
            issue_nodes = self.root_node.children

        # 3. Create Nodes
        for name, node in self.nodes.items():
            
            # Determine Color
            color = "#DDDDDD" 
            
            if hasattr(self, 'root_node') and name == self.root_node.name:
                color = "#000000"       # Root: Black
                width = "0.5"           
                
            elif name in issue_nodes:
                color = "#D55E00"       # Issues: Dark Orange
                width = "0.4"
                
            elif node.children: 
                color = "#0072B2"       # Abstract: Steel Blue
                width = "0.3"
                
            else: 
                color = "#999999"       # Leaf: Medium Grey
                width = "0.2"           

            # Create Node
            pydot_node = pydot.Node(
                name, 
                fillcolor=color,
                width=width
            )
            graph.add_node(pydot_node)

            # Create Edges
            if node.children:
                for child in node.children:
                    edge = pydot.Edge(name, child)
                    graph.add_edge(edge)

        # 4. Save Output
        out_name = filename if filename else f"{self.name}_minimalist.png"
        
        try:
            graph.write_png(out_name)
            print(f"Minimalist graph saved: {out_name}")
        except Exception as e:
            print(f"Graphviz Error: {e}")
    
    def visualiseSubADMs(self, output_dir="sub_adm_viz"):
        """
        Iterates through all evaluated Sub-ADMs and generates visualization graphs for them.
        
        Parameters
        ----------
        output_dir : str
            Directory to save the images (default: "sub_adm_viz")
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        print(f"\n--- Visualising Sub-ADMs to '{output_dir}/' ---")

        for node_name, node in self.nodes.items():
            # Check if this is a SubADMNode by looking for the stored instances fact
            # The key format defined in SubADMNode is: f'{self.name}_sub_adm_instances'
            fact_key = f"{node_name}_sub_adm_instances"
            
            if hasattr(self, 'facts') and fact_key in self.facts:
                sub_instances = self.facts[fact_key]
                
                print(f"Found Sub-ADM results for node: {node_name}")
                
                for item_name, sub_adm_obj in sub_instances.items():
                    # Sanitize filenames
                    safe_node = node_name.replace(" ", "_")
                    safe_item = str(item_name).replace(" ", "_").replace("/", "-")
                    filename = os.path.join(output_dir, f"{safe_node}_{safe_item}.png")
                    
                    # Generate the graph using the sub-ADM's own visualization method
                    # We pass its specific 'case' so the nodes are colored correctly (Green/Red)
                    try:
                        sub_adm_obj.visualiseNetwork(filename=filename, case=sub_adm_obj.case)
                        # Optional: Also generate minimalist version
                        # sub_adm_obj.visualiseMinimalist(filename=filename.replace(".png", "_min.png"))
                    except Exception as e:
                        print(f"  Error visualizing {safe_item}: {e}")
                    
    def addInformationQuestion(self, name, question):
        """
        Adds a simple information question that collects a string answer without creating a BLF
        
        Parameters
        ----------
        name : str
            the name/key to store the information under
        question : str
            the question text to ask the user
        """
        
        if not hasattr(self, 'information_questions'):
            self.information_questions = {}
        
        self.information_questions[name] = question
        
        # Add to question order so it gets processed
        if name not in self.questionOrder:
            self.questionOrder.append(name)

    def setFact(self, fact_name, answer):
        """
        Sets a facts in the ADM which can be referenced in question text 
        
        Parameters
        ----------
        fact_name : str
            the name of the fact
        answer : any
            the corresponding fact
        """
        if not hasattr(self, 'facts'):
            self.facts = {}
        
        if fact_name not in self.facts:
            self.facts[fact_name] = answer
        
    def getFact(self, fact_name):
        """
        Gets a fact for a BLF
        
        Parameters
        ----------
        fact_name : str
            the name of the fact
            
        Returns:
            the value of the fact, or None if not found
        """
        logger.debug(f'fact_name {fact_name} {type(fact_name)}')
        if hasattr(self, 'facts') and fact_name in self.facts:
            return self.facts[fact_name]
        else:
            raise NameError('Fact specified has no value assigned')    
    
    def resolveQuestionTemplate(self, question_text):
        """
        Resolves template variables in question text using collected facts
        
        Parameters
        ----------
        question_text : str
            the question text with template variables like {VARIABLE_NAME}
            
        Returns:
            str: the resolved question text with placeholders replaced
        """
        
        # Look for template variables like {VARIABLE_NAME}
        template_pattern = r'\{([^}]+)\}'
        
        resolved_text = re.sub(template_pattern, self._replace_template, question_text)
        
        return resolved_text
    
    def _replace_template(self, match):
        """
        Facting finding helper function for resolving a question template with a fact variable
        
        Parameters
        -----------
        match: str
            the match from the regex operation looking for a variable to replace
            
        Returns:
        -----------
        variable_name: str
            the fact itself

        """
        variable_name = match.group(1)
        
        # Try to get the fact from the INFORMATION category first
        value = self.getFact(variable_name)
        if value:
            return str(value)
        
        # Show placeholder if not found
        return f"[{variable_name}]"  
        
class Node:
    """
    A class used to represent an individual node, whose acceptance conditions
    are instantiated by 'yes' or 'no' questions

    Attributes
    ----------
    name : str
        the name of the node
    question : str, optional
        the question which will instantiate the blf
    answers : 
        set to None type to indicate to other methods the Node is not from MultiChoice()
    acceptanceOriginal : str
        the original acceptance condition before being converted to postfix notation
    statement : list
        the statements which will be output depending on whether the node is accepted or rejected
    acceptance : list
        the acceptance condition in postfix form
    children : list
        a list of the node's children nodes
    
    Methods
    -------
    attributes(acceptance)
        sets the acceptance conditions and determines the children nodes  
    
    logicConverter(expression)
        converts the acceptance conditions into postfix notation
        
    """
    def __init__(self, name, acceptance=None, statement=None, question=None):
        """
        Parameters
        ----------
        name : str
            the name of the node
        statement : list, optional
            the statements which will be output depending on whether the node is accepted or rejected
        acceptance : list, optional
            the acceptance condition in postfix form
        question : str, optional
            the question which will instantiate the blf
        """
        #name of the node
        self.name = name
        
        #question for base leve factor
        self.question = question
        
        self.answers = None
        
        self.acceptanceOriginal = acceptance
    
        #sets postfix acceptance conditions and children nodes
        try:
            self.attributes(acceptance)
            self.statement = statement
        except:
            self.acceptance = None
            self.children = None
            self.statement = None
    
    def attributes(self, acceptance):
        """
        sets the acceptance condition and children for the node
        
        Parameters
        ----------
        acceptance : list
            the acceptance condition in postfix form
        """
        
        #sets acceptance condition to postfix if acceptance condition specified
        self.acceptance = []
        self.children = []
        
        for i in acceptance:
            self.acceptance.append(self.logicConverter(i))
        
        for i in self.acceptance:
            splitAcceptance = i.split()
            
            #sets the children nodes
            for token in splitAcceptance:
                
                if token not in ['and','or','not','reject','accept'] and token not in self.children:
                    
                    self.children.append(token)   

    def logicConverter(self, expression):
        """
        converts a logical expression from infix to postfix notation
        
        Parameters
        ----------
        expression : list
            the acceptance condition to be converted into postfix form
        """
        
        #precedent dictionary of logical operators and special keywords
        precedent = {'(':1,'or':2,'and':3,'not':4,'reject':5,'accept':5}
        
        #creates the stack
        operatorStack = Stack()
        
        #splits the tokens in the logical expression
        tokenList = expression.split()
        
        #stores the postfix expression
        postfixList = []

        #checks each token in the expression and pushes or pops on the stack accordingly
        for token in tokenList:
            
            if token == '(':
                operatorStack.push(token)
            elif token == ')':
                topToken = operatorStack.pop()
                while topToken != '(':
                    postfixList.append(topToken)
                    topToken = operatorStack.pop()

                            
            elif token == 'and' or token == 'or' or token == 'not' or token == 'reject' or token == 'accept':
                while (not operatorStack.isEmpty()) and (precedent[operatorStack.peek()] >= precedent[token]):
                    postfixList.append(operatorStack.pop())
                operatorStack.push(token)
            
            else:
                postfixList.append(token)

        #while operator stack not empty pop the operators to the postfix list
        while not operatorStack.isEmpty():
            postfixList.append(operatorStack.pop())
        
        #returns the post fix expression as a string  
        return " ".join(postfixList)

    def __str__(self):
        return self.name

class SubADMNode(Node):
    """
    A node that depends on evaluating a sub-ADM for each item from a given list
    
    Attributes
    ----------
    name : str
        the name of the node
    sub_adm_creator : function
        function that creates and returns a sub-ADM instance
    function : str or function
        the function that returns the list of items to evaluate the sub-adm over
    """
    
    def __init__(self, name, sub_adm, function, rejection_condition=False, check_node = []):
        """
        Parameters
        ----------
        name : str
            the name of the node
        sub_adm_creator : function
            function that creates and returns a sub-ADM instance
        function : str or function
            the function that returns the list of items to evaluate the sub-adm over
        """
        
        #initialize as a regular Node
        super().__init__(name, None, [f"{name} evaluation completed"], None)
        
        self.name = name
        self.sub_adm = sub_adm

        #function to generate items to loop through
        self.function = function
        
        self.sub_adm_results = {}
        
        # Override the question to indicate this is a sub-ADM question
        #self.question = f"Sub-ADM evaluation: {name}" #don't understand?
        
        #enables a default reject mode
        self.rejection_condition = rejection_condition
        
        #enables a node to populated from the main_adm into the sub_adm if present
        
        if isinstance(check_node, list):
            self.check_node = check_node
        else:
            raise ValueError('check_node incorrectly specified - expects a list input')
        
    def evaluateSubADMs(self, ui_instance):
        """
        Evaluates sub-ADMs for each item using the existing ADM infrastructure
        
        Parameters
        ----------
        ui_instance : UI
            the UI instance to access the main adm and case
            
        Returns:
            bool: True if BLF should be accepted, False otherwise
        """

        
        self.main_adm = ui_instance.adm
        
        #get the list of items to evaluate
        items = self._get_source_items()
        
        if not items:
            print(f"\nNo items found to evaluate for {self.name}")
            return False
            
        accepted_count = 0
        rejected_count = 0
        item_results = []
        sub_adm_instances = {}  #store sub-ADM instances for later access to statements
        
        print(f"\n=== Evaluating {self.name} for {len(items)} item(s) ===")

        #evaluate sub-ADM for each item using the existing UI infrastructure
        for i, item in enumerate(items, 1):
            print(f"\n--- Item {i}/{len(items)}: {item} ---")
                
            #create a new sub-ADM instance with key facts as the same
            sub_adm = self.sub_adm(item)
            
            if len(self.check_node) > 0:
                
                for node in self.check_node:
                    if node in self.main_adm.case:
                        sub_adm.case.append(node)
                    else:
                        pass
                
            sub_adm.facts = self.main_adm.facts
        
            # Use the existing UI infrastructure to evaluate the sub-ADM
            # This will handle all node types generically (DependentBLF, QuestionInstantiator, etc.)
            sub_result, sub_case, sub_adm = self._evaluateSubADMWithUI(sub_adm, item, ui_instance)
            
            # Store the sub-ADM instance for later access to statements
            sub_adm_instances[item] = sub_adm
            
            logger.debug('3')

            
            self.sub_adm_results[item] = sub_result
            #add the results to a list so we can eval other nodes which use the sub-adm
            item_results.append(sub_case)
            
            if sub_result:
                accepted_count += 1
                print(f"{item}: ACCEPTED")
            else:
                rejected_count += 1
                print(f"{item}: REJECTED")
            
            # except Exception as e:
            #     self.sub_adm_results[item] = 'ERROR'
            #     item_results.append(['ERROR'])
            #     print(f"{item}: ERROR - {e}")
        
        #display summary of Sub-ADMs
        print(f"\nSub-ADM Summary ===")
        print(f"Total items: {len(items)}")
        print(f"Accepted: {accepted_count}")
        print(f"Rejected: {rejected_count}")
        
        #store results in the main ADM for other BLFs to access
        if hasattr(ui_instance.adm, 'setFact'):
            ui_instance.adm.setFact(f'{self.name}_results', item_results)
            ui_instance.adm.setFact(f'{self.name}_accepted_count', accepted_count)
            ui_instance.adm.setFact(f'{self.name}_rejected_count', rejected_count)
            ui_instance.adm.setFact(f'{self.name}_items', items) 
            ui_instance.adm.setFact(f'{self.name}_sub_adm_instances', sub_adm_instances)
        
        #determine final acceptance based on results
        if self.rejection_condition:
            if rejected_count == 0:
                print(f"\n{self.name} is ACCEPTED (no rejected item(s))")
                return True 
            else:
                print(f"\n{self.name} is REJECTED (found {rejected_count} rejected item(s))")
                return False

        else:
            if accepted_count >= 1:
                print(f"\n{self.name} is ACCEPTED (found {accepted_count} accepted item(s))")
                return True
            else:
                print(f"\n{self.name} is REJECTED (no accepted items found)")
                return False
                
    def _get_source_items(self):
        """
        Gets the list of items to evaluate from the source
        
        Parameters
        ----------
        ui_instance : UI
            the UI instance to access the main adm
            
        Returns:
            list: list of items to evaluate
        """
        # Check if source_blf is a function (callable)
        if callable(self.function):
            return self.function(self.main_adm)
        elif isinstance(self.function, list):
            # If source_blf is already a list, return it
            return self.function
        else:
            print(f"ERROR: {self.function} is not a function or a list of items")
            return
    
    def _evaluateSubADMWithUI(self, sub_adm, item, ui_instance):
        """
        Evaluates a single sub-ADM using the existing UI infrastructure
        
        Parameters
        ----------
        sub_adm : ADM
            the sub-ADM instance to evaluate
        item : str
            the item name being evaluated
        ui_instance : UI
            the UI instance to reuse question generation logic
            
        Returns:
            str: 'ACCEPTED', 'REJECTED'
            list: the final case after evaluation
        """
        try:
            print(f"Evaluating sub-ADM for {item}. Please answer the following questions ONLY in relation to this formulation of objective technical problem; do not use conclusions from other objective technical problems to inform your answers.")
            
            # Create a temporary UI instance for this sub-ADM evaluation
            # This allows us to reuse all the existing question generation logic
            temp_ui = type(ui_instance)(sub_adm)  # Create instance of same class
            temp_ui.case = sub_adm.case.copy()
            temp_ui.caseName = item
            
            logger.debug(f"  → Created temp_ui with {len(temp_ui.adm.nodes)} nodes")
            
            # Use the existing UI infrastructure to ask questions and build the case
            # This will handle all node types generically
            temp_ui.ask_questions(temp_ui.adm.nodes.copy(), temp_ui.adm.questionOrder.copy())
            
            print(f"Completed asking questions for {item}")
            
            # Get the final case after evaluation
            final_case = temp_ui.adm.case
            

            if hasattr(temp_ui.adm,'root_node'):
                root_node = temp_ui.adm.root_node.name
            else:
                raise ValueError('no root node specified')
            
            # logger.debug(f"Final case for {item}: {final_case}: {type(final_case)}")
            
            # logger.debug(f'root: {root_node} : {type(root_node)}')
            
            #check if root node accepted
            if root_node in final_case:
                # Root node was accepted
                print(f"- {item} ACCEPTED ({root_node} accepted)")
                return True, final_case, temp_ui.adm
            else:
                # Root node was rejected (not in final_case)
                print(f"- {item} REJECTED ({root_node} rejected)")
                return False, final_case, temp_ui.adm
                
        except Exception as e:
            raise ValueError (f"  → Error evaluating sub-ADM for {item}: {e}")

class GatedBLF(Node):
    """
    A BLF that is only asked if another BLF has been satisfied
    
    Attributes
    ----------
    name : str
        the name of the BLF
    gated_node : str
        the name of the node this BLF depends on
    question_template : str
        the question template that can reference inherited factual ascriptions
    factual_ascription : dict
        additional factual ascriptions for this BLF
    """
    
    def __init__(self, name, gated_node, question_template):
        """
        Parameters
        ----------
        name : str
            the name of the BLF
        gated_node : str
            the name of the node this BLF depends on
        question_template : str
            the question template that can reference inherited factual ascriptions
        """
        
        # Initialize as a regular Node but with special dependency handling
        super().__init__(name, None, None, question_template)
        
         # Handle both single string and list
        if isinstance(gated_node, str):
            self.gated_node = [gated_node]
        else:
            self.gated_node = gated_node
        
        self.question_template = question_template

    def check_gated(self, case):
        """
        Checks if the gated nodes are satisfied
        
        Parameters
        ----------
        adm : adm
            the adm instance
        case : list
            the current case
            
        Returns:
            bool: True if gated is satisfied, False otherwise
        """
        return all(dep_node in case for dep_node in self.gated_node)

class EvaluationNode(Node):
    """
    A node that automatically evaluates based on sub-ADM results from another BLF
    
    Simply checks if a given node name appears in any of the sub-ADM case lists.
    If found in any list -> ACCEPTED, if not found in any list -> REJECTED
    """
    
    def __init__(self, name, source_blf, target_node, statements=None, rejection_condition=False):
        """
        Parameters
        ----------
        name : str
            the name of the BLF
        source_blf : str
            the name of the BLF that contains the sub-ADM results to evaluate
        target_node : str
            the node name to look for in the sub-ADM cases (e.g., 'POSITIVE_RESOURCE')
        statements : list, optional
            statements to show if the BLF is accepted or rejected
        """
        
        # Ensure statements is a list
        if statements is None:
            statements = [f"{name} is accepted", f"{name} is rejected"]
        
        # Initialize as a regular Node
        super().__init__(name, None, statements, None)
        
        # Override the statement that might have been set to None by the parent constructor
        self.statement = statements
        
        self.source_blf = source_blf
        self.target_node = target_node
        self.rejection_condition = rejection_condition
        
        # Override the question to indicate this is an evaluation BLF
        self.question = f"Evaluation: {name} based on {source_blf} results"
    
    def evaluateResults(self, adm):
        """
        Evaluates the sub-ADM results to determine node acceptance
        
        Simply checks if target_node appears in any of the sub-ADM case lists.
        
        Parameters
        ----------
        adm : adm
            the adm instance to get facts from
            
        Returns:
            bool: True if target_node found in any case list, False otherwise
        """
        try:
            
            try:
                item_results = adm.getFact(f'{self.source_blf}_results')
            except:
                return False
                        
            # Get the source items list for display
            #source_items = adm.getFact('{self.source_blf}_items') or []
            logger.debug(f"EVALUATION: {self.name}")
            if self.rejection_condition:
                logger.debug(f"Looking for '{self.target_node}' to not be in {self.source_blf} results")
            else:
                logger.debug(f"Looking for '{self.target_node}' in {self.source_blf} results")
                            
            # Check each sub-ADM case list for the target node
            found_in_items = []
                        
            for i, item_case in enumerate(item_results):
                #logger.debug(f'i: {i}; item case: {item_case}')                    
                
                if isinstance(item_case, list):
                    #logger.debug(f'item name: {item_name}')                    
                    #if i < len(source_items) else f"Item {i+1}"
                    
                    if self.rejection_condition:
                        if self.target_node not in item_case:
                            logger.debug(f"{self.target_node}: {self.target_node} NOT found in case {item_case}")   
                        else:
                            found_in_items.append(self.target_node)
                            logger.debug(f"{self.target_node}: {self.target_node} found in case {item_case}")
                    else:
                        if self.target_node in item_case:
                            found_in_items.append(self.target_node)
                            logger.debug(f"{self.target_node}: {self.target_node} found in case {item_case}")
                        else:
                            logger.debug(f"{self.target_node}: {self.target_node} NOT found in case {item_case}")
                else:
                    print(f"Item {i+1}: Invalid case format - {item_case}")
                
            if found_in_items:
                if self.rejection_condition:
                    logger.debug(f"{self.target_node} IN sub-ADM cases")
                    logger.debug(f"{self.name} is REJECTED")
                    return False
                else:
                    logger.debug(f"{self.target_node}' IN sub-ADM cases")
                    logger.debug(f"{self.name} is ACCEPTED")
                    return True
            else:
                if self.rejection_condition:
                    logger.debug(f"{self.target_node} not found in any sub-ADM cases")
                    logger.debug(f"{self.name} is ACCEPTED")
                    return True
                else:
                    logger.debug(f"{self.target_node} not found in any sub-ADM cases")
                    logger.debug(f"{self.name} is REJECTED")
                    return False
                
        except Exception as e:
            print(f"Error evaluating {self.name}: {e}")
            return False