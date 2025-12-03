
from pythonds import Stack
import pydot

class ADF:
    """
    A class used to represent the ADF graph

    Attributes
    ----------
    name : str
        the name of the ADF
    nodes : dict
        the nodes which constitute the ADF
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
        allows nodes to be added to the ADF from the Node() class
    addMulti(name, acceptance, statement, question)
        allows nodes to be added to the ADF from the MultiChoice() class
    nonLeafGen()
        determines what is a non-leaf factor
    evaluateTree(case)
        evaluates the ADF for a specified case
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
        allows visualisation of the ADF
    saveNew(name)
        allows the ADF to be saved as a .xlsx file
    saveHelper(wb,name)
        helper class for saveNew which provides core functionality
    """
    
    def __init__(self, name):
        """
        Parameters
        ----------
        name : str
            the name of the ADF
        """
      
        self.name = name
        
        #dictionary of nodes --> 'name': 'node object
        self.nodes = {}
        
        self.reject = False
        
        #dictionary of nodes which have children
        self.nonLeaf = {}
        
        self.questionOrder = []

        # Initialize question_instantiators attribute
        self.question_instantiators = {}
        
    def addNodes(self, name, acceptance = None, statement=None, question=None):
        """
        adds nodes to ADF
        
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
        
        node = Node(name, acceptance, statement, question)
        
        self.nodes[name] = node
        
        self.question = question
        
        #creates children nodes
        if node.children != None:
            for childName in node.children:
                if childName not in self.nodes:
                    node = Node(childName)
                    self.nodes[childName] = node

    def addQuestionInstantiator(self, question, blf_mapping, factual_ascription=None, question_order_name=None, dependency_node=None):
        """
        Adds a question that can instantiate BLFs without creating additional nodes in the model
        
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
        dependency_node : str, optional
            the name of the node this question instantiator depends on
        """
        
        # Create a unique name for this question if not provided
        if question_order_name is None:
            question_order_name = f"question_{len(self.questionOrder) + 1}"
        
        # Store the question and mapping in the ADF for later use
        if not hasattr(self, 'question_instantiators'):
            self.question_instantiators = {}
        
        self.question_instantiators[question_order_name] = {
            'question': question,
            'blf_mapping': blf_mapping,
            'factual_ascription': factual_ascription,
            'dependency_node': dependency_node  # Add dependency information
        }
        
        # Add the question to the question order
        if question_order_name not in self.questionOrder:
            self.questionOrder.append(question_order_name)

    def addSubADMBLF(self, name, sub_adf_creator, function, dependency_node=None, rejection_condition=False):
        """
        Adds a BLF that depends on evaluating a sub-ADM for each item
        
        Parameters
        ----------
        name : str
            the name of the BLF to be instantiated
        sub_adf_creator : function
            function that creates and returns a sub-ADM instance
        function : str or function
            the function that returns the list of items to evaluate, or a list of items
        dependency_node : str or list, optional
            the name(s) of the node(s) this BLF depends on
        """
        
        # Create a special node that handles sub-ADM evaluation
        node = SubADMBLF(name, sub_adf_creator, function, dependency_node, rejection_condition)
        self.nodes[name] = node
        
        # Add to question order
        if name not in self.questionOrder:
            self.questionOrder.append(name)
    
    def addEvaluationBLF(self, name, source_blf, target_node, statements=None, rejection_condition=False):
        """
        Adds a BLF that automatically evaluates based on sub-ADM results from another BLF
        
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
        
        # Create a special node that handles result evaluation
        node = EvaluationBLF(name, source_blf, target_node, statements, rejection_condition)
        self.nodes[name] = node
        
        # Add to question order
        if name not in self.questionOrder:
            self.questionOrder.append(name)
    

    def nonLeafGen(self):
        """
        determines which of the nodes is non-leaf        
        """
        
        #sets it back to an empty dictionary
        self.nonLeaf = {}
        
        #checks each node and determines if it is a non-leaf node (one with children)
        for name,node in zip(self.nodes,self.nodes.values()):
            
            #adds node to dict of nodes with children
            if node.children != None and node.children != []:
                self.nonLeaf[name] = node
            # Also include EvaluationBLF nodes even if they don't have children
            elif hasattr(node, 'evaluateResults'):
                self.nonLeaf[name] = node
            else:
                pass
                   
    def evaluateTree(self, case):
        """
        evaluates the ADF for a given case
        
        Parameters
        ----------
        case : list
            the list of factors forming the case 
        
        """
        #keep track of print statements
        self.statements = []
        #list of non-leaf nodes which have been evaluated
        self.nodeDone = []
        self.case = case
        
        # Initialize vis list for tracking attacking nodes
        self.vis = []

        
        #generates the non-leaf nodes
        self.nonLeafGen()
        #while there are nonLeaf nodes which have not been evaluated, evaluate a node in this list in ascending order  
        while self.nonLeaf != {}:

            # Create a copy to avoid "dictionary changed size during iteration" error
            for name,node in zip(list(self.nonLeaf.keys()), list(self.nonLeaf.values())):
                #checks if the node's children are non-leaf nodes
                if name == 'Decide' and len(self.nonLeaf) != 1:
                    pass     
                elif hasattr(node, 'evaluateResults'):
                    # Special handling for EvaluationBLF nodes - handle them first
                    #adds to list of evaluated nodes
                    self.nodeDone.append(name) 
                    
                    # This is an EvaluationBLF - evaluate it and add appropriate statement
                    result = node.evaluateResults(self)
                    if result:
                        # EvaluationBLF was accepted
                        if name not in self.case:
                            self.case.append(name)
                        if hasattr(node, 'statement') and node.statement and len(node.statement) > 0:
                            self.statements.append(node.statement[0])
                    else:
                        # EvaluationBLF was rejected
                        if hasattr(node, 'statement') and node.statement and len(node.statement) > 1:
                            self.statements.append(node.statement[1])
                        elif hasattr(node, 'statement') and node.statement and len(node.statement) > 0:
                            self.statements.append(node.statement[0])
                    
                    # Remove from nonLeaf and continue
                    self.nonLeaf.pop(name)
                    continue
                elif self.checkNonLeaf(node):
                    #adds to list of evaluated nodes
                    self.nodeDone.append(name) 
                    
                    #checks candidate node's acceptance conditions
                    if self.evaluateNode(node):

                        #adds factor to case if present (only if not already there)
                        if name not in self.case:
                            self.case.append(name)
                        else:
                            pass
                        
                        # NEW: Automatically inherit facts when abstract factors are added to case
                        if hasattr(self, 'facts'):
                            
                            # Check if this is an abstract factor (has children)
                            if (hasattr(self.nodes[name], 'children') and 
                                self.nodes[name].children):
                                # Get inherited facts and store them for this abstract factor
                                inherited_facts = self.getInheritedFacts(name, self.case)
                                if inherited_facts:
                                    # Store inherited facts on the abstract factor itself
                                    if name not in self.facts:
                                        self.facts[name] = {}
                                    for fact_name, value in inherited_facts.items():
                                        self.facts[name][fact_name] = value
                                
                        #deletes node from nonLeaf nodes
                        self.nonLeaf.pop(name)
                        self.statements.append(node.statement[self.counter])
                        self.reject = False
                        break

                    #if node's acceptance conditions are false                       
                    else:
                        #deletes node from nonLeaf nodes but doesn't add to case
                        self.nonLeaf.pop(name)
                        #the last statement is always the rejection statemenr
         
                        if self.reject: 
                            self.statements.append(node.statement[self.counter])
                        else:
                            self.statements.append(node.statement[-1])
                        self.reject = False
                        break
                
        # Clean up any duplicates that might have slipped through
        if hasattr(self, 'case') and self.case:
            # Remove duplicates while preserving order
            seen = set()
            unique_case = []
            for item in self.case:
                if item not in seen:
                    seen.add(item)
                    unique_case.append(item)
            
            if len(unique_case) != len(self.case):
                self.case = unique_case
        
        return self.statements
                                  
    def evaluateNode(self, node):
        """
        evaluates a node in respect to its acceptance conditions
        
        x will be always be a boolean value
        
        Parameters
        ----------
        node : class
            the node class to be evaluated
        
        """
        
        #for visualisation purposes - this tracks the attacking nodes
        if not hasattr(self, 'vis'):
            self.vis = []
        
        # Store the current vis list before evaluation
        current_vis = getattr(self, 'vis', []).copy()
        
        #counter to index the statements to be shown to the user
        self.counter = -1
        
        #checks each acceptance condition seperately
        for i in node.acceptance:
            self.reject = False
            self.counter+=1
            x = self.postfixEvaluation(i)
            
            # If this is a reject condition and it's true, return False immediately
            if self.reject and x == True:
                # Merge current vis with the stored vis
                self.vis = list(set(current_vis + self.vis))
                self.reject = True
                return False
            
            # If this is an accept condition and it's true, return True immediately
            if not self.reject and x == True:
                # Merge current vis with the stored vis
                self.vis = list(set(current_vis + self.vis))
                return True

            if x == 'accept':
                return True
                
        # If we get here, no conditions were satisfied
        # Merge current vis with the stored vis
        self.vis = list(set(current_vis + self.vis))
        return False
    
    def postfixEvaluation(self,acceptance):
        """
        evaluates the given acceptance condition in postfix notation
        
        Parameters
        ----------
        acceptance : str
            a string with the names of nodes in postfix notation with logical operators            
        
        """
        #initialises stack of operands
        operandStack = Stack()
        #list of tokens from acceptance conditions
        tokenList = acceptance.split()
        
        #checks each token's acceptance conditions
        for token in tokenList:
            if token == 'accept':
                # Auto-accept condition - push True as a fallback
                operandStack.push(True)
            elif token == 'reject':
                # Pop the operand (which should be a node name)
                operand = operandStack.pop()
                # Always add the operand to vis as it's a rejection condition
                self.vis.append(operand)
                # Check if the node name is in the case
                if operand in self.case:
                    # Node is in case, so we should reject the parent node
                    self.reject = True
                    operandStack.push(True)
                else:
                    # Node is not in case, so we should not reject the parent node
                    self.reject = False
                    operandStack.push(False)
            elif token == 'not':
                operand1 = operandStack.pop()
                result = self.checkCondition(token,operand1)
                operandStack.push(result)
                self.vis.append(operand1)
                
            elif token == 'and' or token == 'or':
                operand2 = operandStack.pop()
                operand1 = operandStack.pop()
                result = self.checkCondition(token,operand1,operand2)
                operandStack.push(result)    
            else:
                # This is a node name - push the node name itself, not a boolean
                operandStack.push(token)
        
        # Check if we have anything on the stack before popping
        if operandStack.isEmpty():
            return False
        final_result = operandStack.pop()
        
        # Convert the final result to a boolean
        if isinstance(final_result, str):
            # If it's a node name, check if it's in the case
            return final_result in self.case
        else:
            # If it's already a boolean, return it as is
            return final_result

    def checkCondition(self, operator, op1, op2 = None):
        """
        checks the logical condition and returns a boolean
        
        Parameters
        ----------
        operator : str
            the logical operator such as or, and, not  
        op1 : str
            the first operand
        op2 : str, optional
            the second operand
        """
        
        if operator == "or":
            if op1 in self.case or op2 in self.case or op1 == True or op2 == True:
                return True
            else:
                return False
            
        elif operator == "and":
            if op1 == True or op1 in self.case:
                if op2 in self.case or op2 == True:
                    return True 
                else: 
                    return False
            elif op2 == True or op2 in self.case:
                if op1 in self.case or op1 == True:
                    return True
                else:
                    return False   
            else:
                return False
            
        elif operator == "not":
            if op1 == True:
                return False
            if op1 == False:
                return True
            elif op1 not in self.case:
                return True
            else:
                return False
        
    def checkNonLeaf(self, node):
        """
        checks if a given node has children which need to be evaluated 
        before it can be evaluated
        
        Parameters
        ----------
        node : class
            the node class to be evaluated
        
        """
        for j in node.children:
    
            if j in self.nonLeaf:
                
                if j in self.nodeDone:
                    pass
                
                else:
                    return False

            else:
                pass

        return True
    
    def getInheritedFacts(self, node_name, case):
        """
        Gets facts inherited from child nodes
        
        Parameters
        ----------
        node_name : str
            the name of the node to get inherited facts for
            
        Returns:
            dict: dictionary of inherited facts
        """
        inherited = {}
        
        if hasattr(self, 'facts') and node_name in self.nodes:
            node = self.nodes[node_name]
            
            if hasattr(node, 'children') and node.children:
                for child_name in node.children:
                    if hasattr(self, 'facts') and child_name in self.facts:
                        for fact_name, value in self.facts[child_name].items():
                            # Don't double the prefix - just use the fact name as is
                            inherited[fact_name] = value
            else:
                pass  # Node has no children
        else:
            pass  # Node not found or no facts attribute
        
        # SPECIAL CASE: If the dependency node is an abstract factor (has children)
        # and it's in the case, automatically inherit facts from related BLFs
        if case and node_name in case:
            # Check if this is an abstract factor (has children)
            if (hasattr(self, 'facts') and hasattr(self, 'nodes') and 
                node_name in self.nodes and 
                hasattr(self.nodes[node_name], 'children') and 
                self.nodes[node_name].children):
                
                # Inherit facts from BLFs that are in the case
                for blf_name, blf_facts in self.facts.items():
                    if blf_name in case:  # Only get facts from BLFs that are in the case
                        for fact_name, value in blf_facts.items():
                            inherited[fact_name] = value
        
        return inherited or {}  # Ensure we never return None
    
    def setFact(self, blf_name, fact_name, value):
        """
        Sets a fact for a BLF
        
        Parameters
        ----------
        blf_name : str
            the name of the BLF
        fact_name : str
            the name of the fact
        value : any
            the value of the fact
        """
        if not hasattr(self, 'facts'):
            self.facts = {}
        
        if blf_name not in self.facts:
            self.facts[blf_name] = {}
        
        self.facts[blf_name][fact_name] = value

    def getFact(self, blf_name, fact_name):
        """
        Gets a fact for a BLF
        
        Parameters
        ----------
        blf_name : str
            the name of the BLF
        fact_name : str
            the name of the fact
            
        Returns:
            the value of the fact, or None if not found
        """
        if hasattr(self, 'facts') and blf_name in self.facts:
            return self.facts[blf_name].get(fact_name)
        return None
    
    def addDependentBLF(self, name, dependency_node, question_template, statements, factual_ascription=None):
        """
        Adds a BLF that depends on another node and inherits its factual ascriptions
        
        Parameters
        ----------
        name : str
            the name of the BLF
        dependency_node : str
            the name of the node this BLF depends on
        question_template : str
            the question template that can reference inherited factual ascriptions
        statements : list
            the statements to show if the BLF is accepted or rejected
        factual_ascription : dict, optional
            additional factual ascriptions for this BLF
        """
        
        # Create a special node that tracks dependencies
        node = DependentBLF(name, dependency_node, question_template, statements, factual_ascription)
        self.nodes[name] = node
        
        # Add to question order
        if name not in self.questionOrder:
            self.questionOrder.append(name)

    def visualiseNetwork(self,case=None):    
        """
        allows the ADF to be visualised as a graph
        
        can be for the domain with or without a case
        
        if there is a case it will highlight the nodes green which have been
        accepted and red the ones which have been rejected        
        
        Parameters
        ----------
        case : list, optional
            the list of factors constituting the case
        """
        
        #initialises the graph
        G = pydot.Dot('{}'.format(self.name), graph_type='graph')
        
        # Set graph direction to top-to-bottom for better hierarchical layout
        G.set_rankdir('TB')

        if case != None:
            # Temporarily set the case for evaluation
            original_case = getattr(self, 'case', None)
            self.case = case
            
            # First, evaluate all nodes to build up self.vis (attacking nodes list)
            self.evaluateTree(case)
            
            #checks each node
            for i in self.nodes.values():
                
                #checks if node is already in the graph
                if i not in G.get_node_list():
                    
                    #checks if the node was accepted in the case
                    if i.name in case:
                        a = pydot.Node(i.name,label=i.name,color='green')
                    else:
                        a = pydot.Node(i.name,label=i.name,color='red')
                                        
                    G.add_node(a)
                
                #creates edges between a node and its children
                if i.children != None and i.children != []:

                    for j in i.children:
                        
                                                
                        if j not in G.get_node_list():
                            
                            if j in case:
                                a = pydot.Node(j,label=j,color='green')
                            else:
                                a = pydot.Node(j,label=j,color='red')
                            
                            G.add_node(a)
                        
                        #self.vis is a list which tracks whether a node is an attacking or defending node
                        if j in self.vis:
                            if j in case:
                                my_edge = pydot.Edge(i.name, j, color='green',label='-')
                            else:
                                my_edge = pydot.Edge(i.name, j, color='red',label='-')
                        else:
                            if j in case:
                                my_edge = pydot.Edge(i.name, j, color='green',label='+')
                            else:
                                my_edge = pydot.Edge(i.name, j, color='red',label='+')

                        G.add_edge(my_edge)
            
            # Restore original case if it existed
            if original_case is not None:
                self.case = original_case
            else:
                delattr(self, 'case')
            
            # Add dependency relationships for DependentBLF and SubADMBLF nodes
            for node_name, node in self.nodes.items():
                if hasattr(node, 'dependency_node') and node.dependency_node:
                    # Handle both single string and list of dependencies
                    if isinstance(node.dependency_node, str):
                        dependency_nodes = [node.dependency_node]
                    else:
                        dependency_nodes = node.dependency_node
                    
                    # Create a dotted black line from dependent node to each dependency node
                    for dep_node in dependency_nodes:
                        dependency_edge = pydot.Edge(node_name, dep_node, 
                                               color='black', style='dotted')
                        G.add_edge(dependency_edge)
            
            
            # Assign ranks to ensure proper hierarchical layout
            self._assign_node_ranks(G)
        
        else:
            
            #creates self.vis if not already created
            self.evaluateTree([])
            
            #checks each node
            for i in self.nodes.values():
                
                #checks if node is already in the graph
                if i not in G.get_node_list():
                    
                    a = pydot.Node(i.name,label=i.name,color='black')

                    G.add_node(a)
                
                #creates edges between a node and its children
                if i.children != None and i.children != []:

                    for j in i.children:
                        
                        if j not in G.get_node_list():
                            
                            a = pydot.Node(j,label=j,color='black')
                           
                            G.add_node(a)
                        
                        #self.vis is a list which tracks whether a node is an attacking or defending node
                        if j in self.vis:
                            my_edge = pydot.Edge(i.name, j, color='black',label='-')
                        else:
                            my_edge = pydot.Edge(i.name, j, color='black',label='+')

                        G.add_edge(my_edge)
            
            # Add dependency relationships for DependentBLF and SubADMBLF nodes (without case)
            for node_name, node in self.nodes.items():
                if hasattr(node, 'dependency_node') and node.dependency_node:
                    # Handle both single string and list of dependencies
                    if isinstance(node.dependency_node, str):
                        dependency_nodes = [node.dependency_node]
                    else:
                        dependency_nodes = node.dependency_node
                    
                    # Create a dotted black line from dependent node to each dependency node
                    for dep_node in dependency_nodes:
                        dependency_edge = pydot.Edge(node_name, dep_node, 
                                               color='black', style='dotted')
                        G.add_edge(dependency_edge)
            
            
            # Assign ranks to ensure proper hierarchical layout
            self._assign_node_ranks(G)
        
        # Legend removed - was causing too many issues
        
        return G
 
    def visualiseNetworkWithSubADMs(self, case=None):
        """
        Creates a comprehensive visualization including main ADM and sub-ADMs side by side
        
        Parameters
        ----------
        case : list, optional
            the list of factors constituting the case
            
        Returns:
            pydot.Dot: combined graph with main ADM and sub-ADMs
        """
        # Create main graph
        main_graph = self.visualiseNetwork(case)
        
        # Create a new combined graph
        combined_graph = pydot.Dot(f'{self.name}_with_subADMs', graph_type='graph')
        combined_graph.set_rankdir('TB')  # Top to bottom for vertical layout
        
        # Add main ADM as a subgraph at the top
        main_subgraph = pydot.Subgraph('cluster_main')
        main_subgraph.set_label(f'Main ADM: {self.name}')
        
        # Copy all nodes and edges from main graph to main subgraph
        for node in main_graph.get_node_list():
            main_subgraph.add_node(node)
        for edge in main_graph.get_edge_list():
            main_subgraph.add_edge(edge)
        
        combined_graph.add_subgraph(main_subgraph)
        
        # Find and create sub-ADMs
        sub_adm_count = 0
        
        # Track which nodes use the same sub-ADM
        sub_adm_mapping = {}
        # Track which nodes should link to which sub-models
        node_to_sub_model = {}
        
        # First pass: identify all sub-ADM creators and create sub-models
        for node_name, node in self.nodes.items():
            if hasattr(node, 'sub_adf_creator'):
                # Check if this sub-ADM creator is already mapped
                sub_adm_key = str(node.sub_adf_creator)
                if sub_adm_key not in sub_adm_mapping:
                    sub_adm_count += 1
                    sub_adm_mapping[sub_adm_key] = sub_adm_count
                
                # Map this node to its sub-model
                current_sub_adm_num = sub_adm_mapping[sub_adm_key]
                node_to_sub_model[node_name] = current_sub_adm_num
                
                # Create sub-ADM instance (only if we haven't created it yet)
                if current_sub_adm_num == sub_adm_count:  # Only create once
                    try:
                        # For visualization, we need to provide a dummy item name
                        # since we don't have actual items to evaluate
                        dummy_item = "visualization_item"
                        sub_adf = node.sub_adf_creator(dummy_item)
                        
                        # Create sub-ADM graph
                        sub_graph = sub_adf.visualiseNetwork()
                        
                        # Create a subgraph to position the sub-model to the right
                        sub_subgraph = pydot.Subgraph(f'cluster_sub_{current_sub_adm_num}')
                        sub_subgraph.set_label(f'Sub-Model {current_sub_adm_num}')
                        
                        # Create a small label node that the red lines will point to
                        # Position it closer to the main ADM
                        label_node = pydot.Node(f"sub_model_label_{current_sub_adm_num}", 
                                               label=f"SUB-MODEL {current_sub_adm_num}",
                                               shape="box",
                                               style="filled",
                                               fillcolor="lightgreen",
                                               width="1.5",
                                               height="0.5")
                        
                        # Add the label node to the main subgraph (not the combined graph)
                        # This positions it within the main ADM area, closer to the nodes
                        main_subgraph.add_node(label_node)
                        
                        # Add all nodes and edges from the sub-ADM to the subgraph
                        for sub_node in sub_graph.get_node_list():
                            sub_subgraph.add_node(sub_node)
                        for sub_edge in sub_graph.get_edge_list():
                            sub_subgraph.add_edge(sub_edge)
                        
                        combined_graph.add_subgraph(sub_subgraph)
                        
                    except Exception as e:
                        print(f"ERROR: Could not create sub-ADM for {node_name}: {e}")
                        import traceback
                        traceback.print_exc()
        
        # Second pass: identify EvaluationBLF nodes that should link to the same sub-models
            for node_name, node in self.nodes.items():
                if hasattr(node, 'source_blf') and node.source_blf in node_to_sub_model:
                    # This is an EvaluationBLF that should link to the same sub-model as its source
                    source_sub_model = node_to_sub_model[node.source_blf]
                    node_to_sub_model[node_name] = source_sub_model
        
        # Third pass: create all connection edges
        for node_name, sub_model_num in node_to_sub_model.items():
            # Add connection edge from main BLF to the label node
            connection_edge = pydot.Edge(
                node_name,
                f"sub_model_label_{sub_model_num}",
                style='dashed',
                color='red',
                penwidth='0.5',
            )
            combined_graph.add_edge(connection_edge)
        
        
        if len(sub_adm_mapping) == 0:
            print("No sub-ADMs found in this ADM")
            # Don't return early - continue to add legend
        
        # Legend removed - was causing too many issues
        
        return combined_graph
    
    def visualiseNetworkMinimal(self, case=None):
        """
        Creates a comprehensive minimalist visualization including main ADM and sub-ADMs side by side
        with no node labels
        
        Parameters
        ----------
        case : list, optional
            the list of factors constituting the case
            
        Returns:
            pydot.Dot: combined graph with main ADM and sub-ADMs (no labels)
        """
        # Create main graph
        main_graph = self.visualiseNetwork(case)
        
        # Create a new combined graph
        combined_graph = pydot.Dot(f'{self.name}_minimal', graph_type='graph')
        combined_graph.set_rankdir('TB')  # Top to bottom for vertical layout
        
        # Force sub-models to stack vertically
        combined_graph.set('ranksep', '1.0')  # Add more space between ranks
        
        # Add main ADM as a subgraph at the top
        main_subgraph = pydot.Subgraph('cluster_main')
        main_subgraph.set_label(f'Main ADM: {self.name}')
        
        # Copy all nodes and edges from main graph to main subgraph
        for node in main_graph.get_node_list():
            # Remove labels and make nodes small and opaque
            node.set_label('')
            node.set_width('0.2')
            node.set_height('0.2')
            node.set_fontsize('0')
            
            # Color code by node type and hierarchy
            node_name = node.get_name()
            if node_name in self.nodes:
                node_obj = self.nodes[node_name]
                
                # Find root node (node with no parents and no dependencies)
                all_children = set()
                for n in self.nodes.values():
                    if hasattr(n, 'children') and n.children:
                        for child in n.children:
                            all_children.add(child)
                
                # Check if this node has any dependencies (DependentBLF nodes that depend on it)
                has_dependencies = False
                for other_node in self.nodes.values():
                    if hasattr(other_node, 'dependency_node') and other_node.dependency_node:
                        if isinstance(other_node.dependency_node, str):
                            if other_node.dependency_node == node_name:
                                has_dependencies = True
                                break
                        elif isinstance(other_node.dependency_node, list):
                            if node_name in other_node.dependency_node:
                                has_dependencies = True
                                break
                
                is_root = node_name not in all_children and not has_dependencies
                
                # Check if this is an immediate child of root (not a BLF)
                is_immediate_child_of_root = False
                if not is_root:
                    for n in self.nodes.values():
                        if hasattr(n, 'children') and n.children and node_name in n.children:
                            # Check if parent is root
                            parent_name = n.name
                            if parent_name not in all_children:  # Parent is root
                                is_immediate_child_of_root = True
                                break
                
                if is_root:
                    # Root node - red
                    node.set_color('red')
                    node.set_fillcolor('red')
                elif is_immediate_child_of_root and hasattr(node_obj, 'children') and node_obj.children:
                    # Immediate child of root that is NOT a BLF (abstract factor) - blue
                    node.set_color('blue')
                    node.set_fillcolor('blue')
                elif hasattr(node_obj, 'children') and node_obj.children:
                    # Other abstract factors - blue
                    node.set_color('blue')
                    node.set_fillcolor('blue')
                else:
                    # Base-level factors - green
                    node.set_color('green')
                    node.set_fillcolor('green')
            else:
                # Default - gray
                node.set_color('gray')
                node.set_fillcolor('gray')
            
            main_subgraph.add_node(node)
        
        # Make edges thinner
        for edge in main_graph.get_edge_list():
            edge.set_penwidth('0.5')
            main_subgraph.add_edge(edge)
        
        combined_graph.add_subgraph(main_subgraph)
        
        # Find and create sub-ADMs
        sub_adm_count = 0
        
        # Track which nodes use the same sub-ADM
        sub_adm_mapping = {}
        # Track which nodes should link to which sub-models
        node_to_sub_model = {}
        
        # First pass: identify all sub-ADM creators and create sub-models
        for node_name, node in self.nodes.items():
            if hasattr(node, 'sub_adf_creator'):
                # Check if this sub-ADM creator is already mapped
                sub_adm_key = str(node.sub_adf_creator)
                if sub_adm_key not in sub_adm_mapping:
                    sub_adm_count += 1
                    sub_adm_mapping[sub_adm_key] = sub_adm_count
                
                # Map this node to its sub-model
                current_sub_adm_num = sub_adm_mapping[sub_adm_key]
                node_to_sub_model[node_name] = current_sub_adm_num
                
                # Create sub-ADM instance (only if we haven't created it yet)
                if current_sub_adm_num == sub_adm_count:  # Only create once
                    try:
                        # For visualization, we need to provide a dummy item name
                        # since we don't have actual items to evaluate
                        dummy_item = "visualization_item"
                        sub_adf = node.sub_adf_creator(dummy_item)
                        
                        # Create sub-ADM graph
                        sub_graph = sub_adf.visualiseNetwork()
                        
                        # Create a subgraph to position the sub-model to the right
                        sub_subgraph = pydot.Subgraph(f'cluster_sub_{current_sub_adm_num}')
                        sub_subgraph.set_label(f'Sub-Model {current_sub_adm_num}')
                        
                        # Create a small label node that the red lines will point to
                        # Position it closer to the main ADM
                        label_node = pydot.Node(f"sub_model_label_{current_sub_adm_num}", 
                                               label=f"SUB-MODEL {current_sub_adm_num}",
                                               shape="box",
                                               style="filled",
                                               fillcolor="lightgreen",
                                               width="1.5",
                                               height="0.5")
                        
                        # Add the label node to the main subgraph (not the combined graph)
                        # This positions it within the main ADM area, closer to the nodes
                        main_subgraph.add_node(label_node)
                        
                        # Add all nodes and edges from the sub-ADM to the subgraph
                        for sub_node in sub_graph.get_node_list():
                            # Remove labels and make sub-ADM nodes small and opaque
                            sub_node.set_label('')
                            sub_node.set_width('0.2')
                            sub_node.set_height('0.2')
                            sub_node.set_fontsize('0')
                            
                            # Color code sub-ADM nodes by type and hierarchy
                            sub_node_name = sub_node.get_name()
                            if hasattr(sub_adf, 'nodes') and sub_node_name in sub_adf.nodes:
                                sub_node_obj = sub_adf.nodes[sub_node_name]
                                
                                # Find root node in sub-ADM (node with no parents and no dependencies)
                                all_children = set()
                                for n in sub_adf.nodes.values():
                                    if hasattr(n, 'children') and n.children:
                                        for child in n.children:
                                            all_children.add(child)
                                
                                # Check if this node has any dependencies (DependentBLF nodes that depend on it)
                                has_dependencies = False
                                for other_node in sub_adf.nodes.values():
                                    if hasattr(other_node, 'dependency_node') and other_node.dependency_node:
                                        if isinstance(other_node.dependency_node, str):
                                            if other_node.dependency_node == sub_node_name:
                                                has_dependencies = True
                                                break
                                        elif isinstance(other_node.dependency_node, list):
                                            if sub_node_name in other_node.dependency_node:
                                                has_dependencies = True
                                                break
                                
                                is_root = sub_node_name not in all_children and not has_dependencies
                                
                                # Check if this is an immediate child of root (not a BLF)
                                is_immediate_child_of_root = False
                                if not is_root:
                                    for n in sub_adf.nodes.values():
                                        if hasattr(n, 'children') and n.children and sub_node_name in n.children:
                                            # Check if parent is root
                                            parent_name = n.name
                                            if parent_name not in all_children:  # Parent is root
                                                is_immediate_child_of_root = True
                                                break
                                
                                if is_root:
                                    # Root node - red
                                    sub_node.set_color('red')
                                    sub_node.set_fillcolor('red')
                                elif is_immediate_child_of_root and hasattr(sub_node_obj, 'children') and sub_node_obj.children:
                                    # Immediate child of root that is NOT a BLF (abstract factor) - blue
                                    sub_node.set_color('blue')
                                    sub_node.set_fillcolor('blue')
                                elif hasattr(sub_node_obj, 'children') and sub_node_obj.children:
                                    # Other abstract factors - blue
                                    sub_node.set_color('blue')
                                    sub_node.set_fillcolor('blue')
                                else:
                                    # Base-level factors - green
                                    sub_node.set_color('green')
                                    sub_node.set_fillcolor('green')
                            else:
                                # Default - gray
                                sub_node.set_color('gray')
                                sub_node.set_fillcolor('gray')
                            
                            sub_subgraph.add_node(sub_node)
                        
                        # Make sub-ADM edges thinner
                        for sub_edge in sub_graph.get_edge_list():
                            sub_edge.set_penwidth('0.5')
                            sub_subgraph.add_edge(sub_edge)
                        
                        combined_graph.add_subgraph(sub_subgraph)
                        
                        # Add invisible edge to force vertical stacking
                        if current_sub_adm_num == 2:
                            # Connect Sub-Model 2 to Sub-Model 1 to force it below
                            combined_graph.add_edge(pydot.Edge(f"sub_model_label_1", f"sub_model_label_2", style='invis'))
                        
                    except Exception as e:
                        print(f"ERROR: Could not create sub-ADM for {node_name}: {e}")
                        import traceback
                        traceback.print_exc()
        
        # Second pass: identify EvaluationBLF nodes that should link to the same sub-models
        for node_name, node in self.nodes.items():
            if hasattr(node, 'source_blf') and node.source_blf in node_to_sub_model:
                # This is an EvaluationBLF that should link to the same sub-model as its source
                source_sub_model = node_to_sub_model[node.source_blf]
                node_to_sub_model[node_name] = source_sub_model
        
        # Third pass: create all connection edges
        for node_name, sub_model_num in node_to_sub_model.items():
            # Add connection edge from main BLF to the label node
            connection_edge = pydot.Edge(
                node_name,
                f"sub_model_label_{sub_model_num}",
                style='dashed',
                color='red',
                penwidth='0.5',
            )
            combined_graph.add_edge(connection_edge)
        
        
        if len(sub_adm_mapping) == 0:
            print("No sub-ADMs found in this ADM")
            # Don't return early - continue to add legend
        
        # Legend removed - was causing too many issues
        
        return combined_graph
    
    
    def _assign_node_ranks(self, G):
        """
        Assign ranks to nodes to ensure proper hierarchical layout
        DependentBLF nodes are positioned at the same level as other BLFs (bottom level)
        """
        # Create subgraphs for different ranks
        rank_0 = pydot.Subgraph(rank='same')
        rank_1 = pydot.Subgraph(rank='same')
        
        # Rank 0: Abstract factors (nodes with children) - top level
        # Rank 1: Base level factors (BLFs) and DependentBLFs - bottom level
        
        for node_name, node in self.nodes.items():
            if node.children and node.children != []:
                # Abstract factors go to rank 0 (top level)
                rank_0.add_node(pydot.Node(node_name))
            else:
                # Base level factors and DependentBLFs go to rank 1 (bottom level)
                rank_1.add_node(pydot.Node(node_name))
        
        # Add subgraphs to the main graph
        if rank_0.get_node_list():
            G.add_subgraph(rank_0)
        if rank_1.get_node_list():
            G.add_subgraph(rank_1)

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
        if not hasattr(self, 'getFact'):
            return question_text
        
        # Look for template variables like {VARIABLE_NAME}
        import re
        template_pattern = r'\{([^}]+)\}'
        
        def replace_template(match):
            variable_name = match.group(1)
            
            # Try to get the fact from the INFORMATION category first
            value = self.getFact('INFORMATION', variable_name)
            if value:
                return str(value)
            
            # If not found in INFORMATION, try to find it as a direct fact
            # This would handle cases where the fact name is the same as the variable
            if hasattr(self, 'facts') and variable_name in self.facts:
                # Check if it's a direct fact (not nested under INFORMATION)
                if isinstance(self.facts[variable_name], dict):
                    # It's a nested fact structure, try to get a default value
                    if 'value' in self.facts[variable_name]:
                        return str(self.facts[variable_name]['value'])
                    elif 'name' in self.facts[variable_name]:
                        return str(self.facts[variable_name]['name'])
                else:
                    # It's a direct value
                    return str(self.facts[variable_name])
            
            # If still not found, try to get it from any other fact categories
            if hasattr(self, 'facts'):
                for category in self.facts:
                    if category != 'INFORMATION':  # Skip INFORMATION since we already checked
                        if variable_name in self.facts[category]:
                            value = self.facts[category][variable_name]
                            if value:
                                return str(value)
            
            return f"[{variable_name}]"  # Show placeholder if not found
        
        resolved_text = re.sub(template_pattern, replace_template, question_text)
        return resolved_text

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

class SubADMBLF(Node):
    """
    A BLF that depends on evaluating a sub-ADM for each item from another BLF
    
    Attributes
    ----------
    name : str
        the name of the BLF
    sub_adf_creator : function
        function that creates and returns a sub-ADM instance
    function : str or function
        the function that returns the list of items to evaluate the sub-adm over
    dependency_node : list
        the names of the nodes this BLF depends on
    """
    
    def __init__(self, name, sub_adf_creator, function, dependency_node=None, rejection_condition=False):
        """
        Parameters
        ----------
        name : str
            the name of the BLF
        sub_adf_creator : function
            function that creates and returns a sub-ADM instance
        function : str or function
            the function that returns the list of items to evaluate the sub-adm over
        dependency_node : str or list, optional
            the name(s) of the node(s) this BLF depends on
        """
        
        # Initialize as a regular Node - no statements needed since sub-ADM handles them
        super().__init__(name, None, [f"{name} evaluation completed"], None)
        
        self.sub_adf_creator = sub_adf_creator
        self.function = function
        self.sub_adf_results = {}
        
        # Handle both single string and list of dependencies
        if dependency_node is None:
            self.dependency_node = []
        elif isinstance(dependency_node, str):
            self.dependency_node = [dependency_node]
        else:
            self.dependency_node = dependency_node
        
        # Override the question to indicate this is a sub-ADM question
        self.question = f"Sub-ADM evaluation: {name}"
        self.rejection_condition = rejection_condition
    
    def checkDependency(self, adf, case):
        """
        Checks if the dependency nodes are satisfied
        
        Parameters
        ----------
        adf : ADF
            the ADF instance
        case : list
            the current case
            
        Returns:
            bool: True if all dependencies are satisfied, False otherwise
        """
        if not self.dependency_node:
            return True  # No dependencies, always satisfied
        
        return all(dep_node in case for dep_node in self.dependency_node)
    
    def _get_source_items(self, ui_instance):
        """
        Gets the list of items to evaluate from the source
        
        Parameters
        ----------
        ui_instance : UI
            the UI instance to access the main ADF
            
        Returns:
            list: list of items to evaluate
        """
        # Check if source_blf is a function (callable)
        if callable(self.function):
            # If source_blf is a function, call it with key facts
            key_facts = self._collect_key_facts(ui_instance)
            return self.function(ui_instance, key_facts)
        elif isinstance(self.function, list):
            # If source_blf is already a list, return it
            return self.function
        else:
            print(f"ERROR: {self.function} is not a function or a list of items")
            return

    def _collect_key_facts(self, ui_instance):
        """
        Collects key facts from the main ADM to pass to sub-ADMs
        
        Parameters
        ----------
        ui_instance : UI
            the UI instance that contains the case and facts
            
        Returns
        -------
        dict: dictionary of key facts
        """
        key_facts = {}
        
        # Get facts from the main ADF
        if hasattr(ui_instance.adf, 'facts'):
            key_facts.update(ui_instance.adf.facts)
        
        # Get inherited facts from dependency nodes if this SubADMBLF has dependencies
        if hasattr(self, 'dependency_node') and self.dependency_node:
            for dep_node in self.dependency_node:
                if hasattr(ui_instance.adf, 'getInheritedFacts'):
                    dep_facts = ui_instance.adf.getInheritedFacts(dep_node, ui_instance.case)
                    if isinstance(dep_facts, dict):
                        key_facts.update(dep_facts)
        
        # Add main case information to key facts
        if hasattr(ui_instance, 'case'):
            key_facts['main_case'] = ui_instance.case
        
        return key_facts

    def evaluateSubADMs(self, ui_instance):
        """
        Evaluates sub-ADMs for each item using the existing ADM infrastructure
        
        Parameters
        ----------
        ui_instance : UI
            the UI instance to access the main ADF and case
            
        Returns:
            bool: True if BLF should be accepted, False otherwise
        """
        try:
            # Get the list of items to evaluate
            items = self._get_source_items(ui_instance)
            
            if not items:
                print(f"\nNo items found to evaluate for {self.name}")
                return False
            
            accepted_count = 0
            rejected_count = 0
            item_results = []
            sub_adf_instances = []  # Store sub-ADM instances for later access to statements
            
            print(f"\n=== Evaluating {self.name} for {len(items)} item(s) ===")
            
            # Collect key facts from the main ADM to pass to sub-ADMs
            key_facts = self._collect_key_facts(ui_instance)

            # Evaluate sub-ADM for each item using the existing UI infrastructure
            for i, item in enumerate(items, 1):
                print(f"\n--- Item {i}/{len(items)}: {item} ---")
                try:
                    # Create a new sub-ADM instance with key facts
                    sub_adf = self.sub_adf_creator(item, key_facts)
                    
                    # Set the item name in the sub-ADM
                    if hasattr(sub_adf, 'setFact'):
                        sub_adf.setFact('ITEM', 'name', item)
                    
                    # Pass key facts to the sub-ADM
                    if key_facts:
                        if hasattr(sub_adf, 'facts'):
                            sub_adf.facts.update(key_facts)
                        else:
                            sub_adf.facts = key_facts.copy()
                        print(f"Passed {len(key_facts)} key facts to sub-ADM for {item}")
                    
                    # Store the sub-ADM instance for later access to statements
                    sub_adf_instances.append(sub_adf)
                    
                    # Use the existing UI infrastructure to evaluate the sub-ADM
                    # This will handle all node types generically (DependentBLF, QuestionInstantiator, etc.)
                    sub_result, sub_case = self._evaluateSubADMWithUI(sub_adf, item, ui_instance)
                    
                    self.sub_adf_results[item] = sub_result
                    item_results.append(sub_case)
                    
                    if sub_result == 'ACCEPTED':
                        accepted_count += 1
                        print(f"✓ {item}: ACCEPTED")
                    elif sub_result == 'REJECTED':
                        rejected_count += 1
                        print(f"✗ {item}: REJECTED")
                    else:
                        print(f"? {item}: UNKNOWN")
                        
                except Exception as e:
                    self.sub_adf_results[item] = 'ERROR'
                    item_results.append(['ERROR'])
                    print(f"✗ {item}: ERROR - {e}")
            
            # Display summary
            print(f"\n=== {self.name} Evaluation Summary ===")
            print(f"Total items: {len(items)}")
            print(f"Accepted: {accepted_count}")
            print(f"Rejected: {rejected_count}")
            print(f"Unknown: {len(items) - accepted_count - rejected_count}")
            
            # Store the detailed results in the main ADF for other BLFs to access
            if hasattr(ui_instance.adf, 'setFact'):
                ui_instance.adf.setFact(self.name, 'results', item_results)
                ui_instance.adf.setFact(self.name, 'accepted_count', accepted_count)
                ui_instance.adf.setFact(self.name, 'rejected_count', rejected_count)
                ui_instance.adf.setFact(self.name, 'items', items)  # Store the item names for display
                ui_instance.adf.setFact(self.name, 'sub_adf_instances', sub_adf_instances)  # Store sub-ADM instances for statements
            
            # Determine final acceptance based on results

            if self.rejection_condition:
                if rejected_count < 1:
                    print(f"\n✓ {self.name} is ACCEPTED (found {accepted_count} accepted item(s))")
                    return True 
                else:
                    print(f"\n✗ {self.name} is REJECTED (no accepted items found)")
                    return False

            else:
                if accepted_count >= 1:
                    print(f"\n✓ {self.name} is ACCEPTED (found {accepted_count} accepted item(s))")
                    return True
                else:
                    print(f"\n✗ {self.name} is REJECTED (no accepted items found)")
                    return False
                    
        except Exception as e:
            print(f"\n✗ Error evaluating {self.name}: {e}")
            return False
    
    def _evaluateSubADMWithUI(self, sub_adf, item, ui_instance):
        """
        Evaluates a single sub-ADM using the existing UI infrastructure
        
        Parameters
        ----------
        sub_adf : ADF
            the sub-ADM instance to evaluate
        item : str
            the item name being evaluated
        ui_instance : UI
            the UI instance to reuse question generation logic
            
        Returns:
            str: 'ACCEPTED', 'REJECTED', or 'UNKNOWN'
            list: the final case after evaluation
        """
        try:
            print(f"  Evaluating sub-ADM for {item}...")
            
            # Create a temporary UI instance for this sub-ADM evaluation
            # This allows us to reuse all the existing question generation logic
            temp_ui = type(ui_instance)()  # Create instance of same class
            temp_ui.adf = sub_adf
            temp_ui.case = sub_adf.case.copy()
            temp_ui.caseName = item
            
            print(f"  → Created temp_ui with {len(temp_ui.adf.nodes)} nodes")
            
            # Use the existing UI infrastructure to ask questions and build the case
            # This will handle all node types generically
            temp_ui.ask_questions()
            
            print(f"  → Completed ask_questions for {item}")
            
            # Get the final case after evaluation
            final_case = temp_ui.case
            print(f"  → Final case for {item}: {final_case}")
            
            # Determine the result based on whether the root node is accepted or rejected
            # The root node is the final node that gets evaluated (corresponds to final statement in explanation)
            # We need to find the node that was evaluated last during the ask_questions process
            # This is the node that determines the final acceptance/rejection
            root_node = None
            
            # Find the node that was evaluated last by looking at the evaluation order
            # The final node is typically the one that corresponds to the final statement
            # We can identify it by looking at which node was processed last in the evaluation
            if hasattr(temp_ui.adf, 'statements') and temp_ui.adf.statements and hasattr(temp_ui.adf, 'nodes') and temp_ui.adf.nodes:
                # The final statement corresponds to the final evaluated node
                # We need to find which node this statement belongs to
                final_statement = temp_ui.adf.statements[-1]
                # Find the node that has this statement
                for node_name, node in temp_ui.adf.nodes.items():
                    if hasattr(node, 'statement') and node.statement and final_statement in node.statement:
                        root_node = node_name
                        break
            
            # Fallback: if we can't find the root node from statements, use the last node in question order
            if not root_node:
                print(f"  → {item} classification: UNKNOWN (no root node found)")
                return 'UNKNOWN', final_case
            
            if root_node in final_case:
                # Root node was accepted
                print(f"  → {item} classified as {root_node} (ACCEPTED)")
                return 'ACCEPTED', final_case
            else:
                # Root node was rejected (not in final_case)
                print(f"  → {item} REJECTED (root node {root_node} rejected)")
                return 'REJECTED', final_case
                
        except Exception as e:
            print(f"  → Error evaluating sub-ADM for {item}: {e}")
            return 'UNKNOWN', []

class DependentBLF(Node):
    """
    A BLF that depends on another node and inherits its factual ascriptions
    
    Attributes
    ----------
    name : str
        the name of the BLF
    dependency_node : str
        the name of the node this BLF depends on
    question_template : str
        the question template that can reference inherited factual ascriptions
    statements : list
        the statements to show if the BLF is accepted or rejected
    factual_ascription : dict
        additional factual ascriptions for this BLF
    """
    
    def __init__(self, name, dependency_node, question_template, statements, factual_ascription=None):
        """
        Parameters
        ----------
        name : str
            the name of the BLF
        dependency_node : str
            the name of the node this BLF depends on
        question_template : str
            the question template that can reference inherited factual ascriptions
        statements : list
            the statements to show if the BLF is accepted or rejected
        factual_ascription : dict, optional
            additional factual ascriptions for this BLF
        """
        
        # Initialize as a regular Node but with special dependency handling
        super().__init__(name, None, statements, question_template)
        
         # Handle both single string and list
        if isinstance(dependency_node, str):
            self.dependency_node = [dependency_node]
        else:
            self.dependency_node = dependency_node

        self.factual_ascription = factual_ascription or {}
        
        # Override the question to be dynamic
        self.question_template = question_template
        self.question = question_template  # Will be resolved dynamically
    
    def resolveQuestion(self, adf, case=None):
        """
        Resolves the question template by replacing placeholders with inherited facts
        
        Parameters
        ----------
        adf : ADF
            the ADF instance to get facts from
        case : list, optional
            the current case to get facts from
        """
        question_text = self.question_template
        
        # First, resolve any template variables using the ADF's template resolution
        question_text = adf.resolveQuestionTemplate(question_text)
        
        # Then, get inherited facts from the dependency nodes and replace any remaining placeholders
        # For multiple dependencies, we need to combine facts from all dependency nodes
        inherited = {}
        
        # Handle both single string and list of dependencies
        if isinstance(self.dependency_node, str):
            dependency_nodes = [self.dependency_node]
        else:
            dependency_nodes = self.dependency_node
        
        # Collect facts from all dependency nodes
        for dep_node in dependency_nodes:
            if isinstance(dep_node, str):  # Safety check
                dep_inherited = adf.getInheritedFacts(dep_node, case)
                if isinstance(dep_inherited, dict):
                    inherited.update(dep_inherited)
        
        # Safety check: ensure inherited is a dictionary
        if not isinstance(inherited, dict):
            inherited = {}
        
        # Replace placeholders in the question template
        # This is now generic - any placeholder like {ICE_CREAM_flavour} will be replaced
        for key, value in inherited.items():
            placeholder = "{" + key + "}"
            if placeholder in question_text:
                question_text = question_text.replace(placeholder, str(value))
        
        # Clean up any remaining unresolved placeholders and format the question nicely
        import re
        # Remove any remaining {placeholder} patterns
        question_text = re.sub(r'\{[^}]+\}', '', question_text)
        # Clean up extra commas and spaces
        question_text = question_text.replace('  ', ' ').strip()
        question_text = question_text.rstrip(',').strip()
        
        return question_text

    def checkDependency(self, adf, case):
        """
        Checks if the dependency nodes are satisfied
        
        Parameters
        ----------
        adf : ADF
            the ADF instance
        case : list
            the current case
            
        Returns
        Returns:
            bool: True if dependency is satisfied, False otherwise
        """
        return all(dep_node in case for dep_node in self.dependency_node)

class SubADM(ADF):
    """
    A specialized ADF class for sub-ADMs that automatically resolves {item} placeholders
    with the actual item name being evaluated.
    
    This class inherits everything from ADF but overrides addNodes to automatically
    replace {item} placeholders in questions with the item_name.
    """
    
    def __init__(self, name, item_name):
        """
        Parameters
        ----------
        name : str
            the name of the sub-ADM
        item_name : str
            the name of the item being evaluated (e.g., "d", "e", etc.)
        """
        super().__init__(name)
        self.item_name = item_name
    
    def addNodes(self, name, acceptance=None, statement=None, question=None):
        """
        Override addNodes to automatically resolve {item} placeholders in questions
        
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
        # Resolve {item} placeholder in question if present
        if question and '{item}' in question:
            resolved_question = question.replace('{item}', self.item_name)
            question = resolved_question
        
        # Call the parent class method
        super().addNodes(name, acceptance, statement, question)

class EvaluationBLF(Node):
    """
    A BLF that automatically evaluates based on sub-ADM results from another BLF
    
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
    
    def evaluateResults(self, adf):
        """
        Evaluates the sub-ADM results to determine BLF acceptance
        
        Simply checks if target_node appears in any of the sub-ADM case lists.
        
        Parameters
        ----------
        adf : ADF
            the ADF instance to get facts from
            
        Returns:
            bool: True if target_node found in any case list, False otherwise
        """
        try:
            # Get the detailed results from the source BLF
            if not hasattr(adf, 'getFact'):
                print(f"Warning: ADF does not have getFact method")
                return False
            
            detailed_results = adf.getFact(self.source_blf, 'results')
            if not detailed_results:
                print(f"Warning: No results found from {self.source_blf}")
                return False
            
            # Get the source items list for display
            source_items = adf.getFact(self.source_blf, 'items') or []
            
            print(f"\n{'='*50}")
            print(f"EVALUATION: {self.name}")
            if self.rejection_condition:
                print(f"Looking for '{self.target_node}' to not be in {self.source_blf} results")
            else:
                print(f"Looking for '{self.target_node}' in {self.source_blf} results")
            print(f"{'='*50}")
            
            # Check each sub-ADM case list for the target node
            found_in_items = []
            
            for i, item_case in enumerate(detailed_results):
                if isinstance(item_case, list):
                    item_name = source_items[i] if i < len(source_items) else f"Item {i+1}"

                    if self.rejection_condition:
                        if self.target_node not in item_case:
                            found_in_items.append(item_name)
                            print(f"✓ {item_name}: {self.target_node} NOT found in case {item_case}")   
                        else:
                            print(f"✗ {item_name}: {self.target_node} found in case {item_case}")
                    else:
                        if self.target_node in item_case:
                            found_in_items.append(item_name)
                            print(f"✓ {item_name}: {self.target_node} found in case {item_case}")
                        else:
                            print(f"✗ {item_name}: {self.target_node} NOT found in case {item_case}")
                else:
                    print(f"Item {i+1}: Invalid case format - {item_case}")
            
            print(f"\n{'='*50}")
            
            if found_in_items:
                print(f"✓ {self.name} is ACCEPTED")
                if self.rejection_condition:
                    print(f"  Found '{self.target_node}' NOT in: {', '.join(found_in_items)}")
                else:
                    print(f"  Found '{self.target_node}' in: {', '.join(found_in_items)}")
                return True
            else:
                print(f"✗ {self.name} is REJECTED")
                print(f"  '{self.target_node}' not found in any sub-ADM cases")
                return False
                
        except Exception as e:
            print(f"✗ Error evaluating {self.name}: {e}")
            return False