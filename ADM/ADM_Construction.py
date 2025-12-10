"""
Creates the classes used to instantiate the Inventive Step ADM and core traversal functionalities

Last Updated: 04.12.25

Status: In Progress
        - Main ADM - DONE
        - SUB-ADM - Delete commented code- if so add_nodes is redundant
        - SubADMBLF - In Progress
"""

from pythonds import Stack
import pydot
import re

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
      
        self.name = name
        #dictionary of nodes --> 'name': 'node object
        self.nodes = {}

        #initialise reject flag as False
        self.reject = False
        
        #dictionary of nodes which have children
        self.nonLeaf = {}
        self.questionOrder = []
        self.question_instantiators = {}
        
    def addNodes(self, name, acceptance = None, statement=None, question=None):
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

    def addSubADMBLF(self, name, sub_adf_creator, function, gating_node=None, rejection_condition=False):
        """
        Adds a BLF that depends on evaluating a sub-ADM for each item i.e. the linking node between the main ADM and the Sub-ADM
        
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
        
        #creates a node that handles sub-ADM evaluation
        node = SubADMBLF(name, sub_adf_creator, function, gating_node, rejection_condition)
        self.nodes[name] = node
        
        #add to question order
        if name not in self.questionOrder:
            self.questionOrder.append(name)
    
    def addEvaluationBLF(self, name, source_blf, target_node, statements=None, rejection_condition=False):
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
        node = EvaluationBLF(name, source_blf, target_node, statements, rejection_condition)
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
        self.node_done = []
        self.case = case

        #generates the non-leaf nodes
        self.nonLeafGen()
        #while there are nonLeaf nodes which have not been evaluated, evaluate a node in this list in ascending order  
        while self.nonLeaf != {}:

            #create a copy to avoid "dictionary changed size during iteration" error
            for name,node in zip(list(self.nonLeaf.keys()), list(self.nonLeaf.values())):

                #special handling for EvaluationBLF nodes - handle them first
                if hasattr(node, 'evaluateResults'):
                    #adds to list of evaluated nodes
                    self.node_done.append(name) 
                    
                    #evaluate it and add appropriate statement
                    result = node.evaluateResults(self)
                    
                    if result:
                        #EvaluationBLF was accepted
                        if name not in self.case:
                            self.case.append(name)
                        if hasattr(node, 'statement') and node.statement:
                            self.statements.append(node.statement[0])
                    else:
                        # EvaluationBLF was rejected
                        if hasattr(node, 'statement') and node.statement:
                            self.statements.append(node.statement[1])
                        else:
                            raise IndexError
                    
                    # Remove from nonLeaf and continue
                    self.nonLeaf.pop(name)
                
                elif self.checkNonLeaf(node):
                    #adds to list of evaluated nodes
                    self.nodeDone.append(name) 
                    
                    #checks candidate node's acceptance conditions
                    
                    #if they are satisfied
                    if self.evaluateNode(node):

                        #adds factor to case if present (only if not already there)
                        if name not in self.case:
                            self.case.append(name)
                        else:
                            pass
                                
                        #deletes node from nonLeaf nodes
                        self.nonLeaf.pop(name)
                        self.statements.append(node.statement[self.counter])
                        self.reject = False
                        break

                    #if not satisfied                     
                    else:
                        #deletes node from nonLeaf nodes but doesn't add to case
                        self.nonLeaf.pop(name)
                        
                        #the last statement is always the rejection statement         
                        if self.reject: 
                            self.statements.append(node.statement[self.counter])
                        else:
                            self.statements.append(node.statement[-1])
                        self.reject = False
                        break
                
        #clean up any duplicates
        self.case = list(set(self.case))
        
        return self.statements
                                  
    def evaluateNode(self, node):
        """
        evaluates a node in respect to its acceptance conditions
        
        will always return a boolean value
        
        Parameters
        ----------
        node : class
            the node class to be evaluated
        
        """
        
        #counter to index the statements to be shown to the user
        self.counter = -1
        
        #checks each acceptance condition seperately
        for i in node.acceptance:
            self.reject = False
            self.counter+=1
            
            
            eval = self.postfixEvaluation(i)
            
            # If this is a reject condition and it's true, return False immediately
            if self.reject and eval is True:
                self.reject = True
                return False
            
            # If this is an accept condition and it's true, return True immediately
            if not self.reject and eval is True:
                return True

            if eval == 'accept':
                return True
    
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
            print(token)
            if token == 'accept':
                #auto-accept condition - push True as a fallback
                operandStack.push(True)
            
            elif token == 'reject':
                #pop the operand (which should be a node name)
                operand = operandStack.pop()

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
                #pop the node name
                operand1 = operandStack.pop()
                
                #check condition validity
                result = self.checkCondition(token,operand1)
                operandStack.push(result)
                
            elif token == 'and' or token == 'or':
                #pop both node names
                operand2 = operandStack.pop()
                operand1 = operandStack.pop()
                
                #check condition validity
                result = self.checkCondition(token,operand1,operand2)
                operandStack.push(result)    
            
            else:
                #this is a node name - push the node name itself, not a boolean
                operandStack.push(token)
        
        #check if we have anything on the stack before popping
        if operandStack.isEmpty():
            return False
        else:
            final_result = operandStack.pop()
        
        #convert the final result to a boolean
        if isinstance(final_result, str):
            #if it's a node name, check if it's in the case
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
        
        #evals disjunctive condition
        if operator == "or":
            if op1 in self.case or op2 in self.case or op1 == True or op2 == True:
                return True
            else:
                return False
        
         #evals conjunctive condition
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
        
        #evals negative condition
        elif operator == "not":
            if op1 == True:
                return False
            if op1 == False:
                return True
            elif op1 not in self.case:
                return True
            else:
                return False
    
    def addGatedBLF(self, name, gated_node, question_template, statements):
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
        node = GatedBLF(name, gated_node, question_template, statements)
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
        if hasattr(self, 'facts') and fact_name in self.facts:
            return self.facts[fact_name]
        else:
            return NameError('Fact specified has no value asigned')    
    
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
        
        resolved_text = re.sub(template_pattern, self.replace_template, question_text)
        
        return resolved_text
    
    def replace_template(self, match):
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
        
class SubADM(ADM):
    """
    A specialized ADF class for sub-ADMs
    
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
            the name of the item being evaluated 
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
        # # Resolve {item} placeholder in question if present
        # if question and '{item}' in question:
        #     resolved_question = question.replace('{item}', self.item_name)
        #     question = resolved_question
        
        # Call the parent class method
        super().addNodes(name, acceptance, statement, question)

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
    
    #CHANGE
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

class GatedBLF(Node):
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
    
    #CHANGE
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