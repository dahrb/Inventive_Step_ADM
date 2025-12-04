from ADM_Construction import ADM,Node

example = ADM('test')
example.case = ['a','b','c']
node = Node('test1',["a and b and ( c or d )",'accept'])
print(node.acceptance)
answer = example.postfixEvaluation(node.acceptance[0])
print(answer)