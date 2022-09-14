"""
Reading Turtle files

(c) 2022 Fabian M. Suchanek
"""

import gzip
import os
import sys
from io import StringIO
import Prefixes

TEST=True

##########################################################################
#             Parsing Turtle
##########################################################################

def printError(*args, **kwargs):
    """ Prints an error to StdErr """
    print(*args, file=sys.stderr, **kwargs)

def charsOfFile(file, message=None):
    """ Iterator over the chars of a GZ or text file, with progress bar """
    if not message:
       message="  Parsing"
    print(message,"...", end="", flush=True)
    totalNumberOfDots=60-len(message)
    coveredSize=0
    printedDots=0
    fileSize=os.path.getsize(file)
    isGZ=file.endswith(".gz")
    if isGZ:
        fileSize*=20
    with (gzip.open(file, mode='rt', encoding='UTF-8') if isGZ else open(file, mode='rt', encoding='UTF-8')) as input:
        while True:
            char=input.read(1)
            if not char:
                break
            coveredSize+=1
            if coveredSize / fileSize * totalNumberOfDots > printedDots:
                print(".", end="", flush=True)
                printedDots+=1
            yield char
    print("done")
    # Yield a few None's so that following code has the occasion to understand the file is over
    yield None
    yield None
    yield None
    yield None
        
def termsAndSeparators(generator):
    """ Iterator over the terms of a char-generator """
    pushBack=None
    while True:
        # Scroll to next term
        while True:
            char=pushBack if pushBack else next(generator)
            pushBack=None
            if not char: 
                # end of file
                yield None                
                return
            elif char=='@':
                # @base and @prefix
                for term in termsAndSeparators(generator):
                    if not term:
                        printError("Unexpected end of file in directive")
                        return
                    if term=='.':
                        break
            elif char=='#':
                # comments
                while char and char!='\n':
                    char=next(generator)
            elif char.isspace():
                # whitespace
                pass
            else:
                break
                
        # Strings
        if char=='"':
            secondChar=next(generator)
            thirdChar=next(generator)
            if secondChar=='"' and thirdChar=='"':
                # long string quote
                literal=""
                while True:
                    char=next(generator)
                    if char:
                        literal=literal+char
                    else:
                        printError("Unexpected end of file in literal",literal)
                        literal=literal+'"""'
                        break
                    if literal.endswith('"""'):
                        break
                literal=literal[:-3]
            else:
                # Short string quote
                if secondChar=='"':
                    literal=''
                    char=thirdChar
                elif thirdChar=='"' and secondChar!='\\':
                    literal=secondChar
                    char=None
                else:    
                    literal=secondChar+thirdChar
                    while True:
                        char=next(generator)
                        if not char:
                            printError("Unexpected end of file in literal",literal)
                            break
                        if char=='"' and not literal.endswith('\\'):
                            break
                        literal=literal+char
            # Make all literals simple literals without line breaks
            literal=literal.replace('\n','\\n').replace('\t','\\t').replace('\r','')
            char=next(generator)
            if char=='^':
                # Datatypes
                next(generator)
                datatype=""
                while True:
                    char=next(generator)
                    if not char:
                        printError("Unexpected end of file in datatype of",literal)
                        break
                    if char!=':' and (char<'A' or char>'z'):
                        break
                    datatype=datatype+char
                if not datatype or len(datatype)<3:
                    printError("Invalid literal datatype:", datatype)
                pushBack=char
                yield('"'+literal+'"^^'+datatype)
            elif char=='@':
                # Languages
                language=""
                while True:
                    char=next(generator)
                    if not char:
                        printError("Unexpected end of file in language of",literal)
                        break
                    if char!='-' and (char<'A' or char>'z'):
                        break
                    language=language+char
                if not language or len(language)>10 or len(language)<2:
                    printError("Invalid literal language:", language)
                pushBack=char
                yield('"'+literal+'"@'+language)
            else:
                pushBack=char
                yield('"'+literal+'"')
        elif char=='<':
            # URIs
            uri=""
            while char!='>':
                uri=uri+char
                char=next(generator)
                if not char:
                    printError("Unexpected end of file in URL",uri)
                    break
            yield uri+">"
        elif char in ['.',',',';','[',']','(',')']:
            # Separators
            yield char
        else:
            # Local names
            iri=""
            while not char.isspace() and char not in ['.',',',';','[',']','"',"'",'^','@','(',')']:
                iri=iri+char
                char=next(generator)
                if not char:
                    printError("Unexpected end of file in IRI",iri)
                    break
            pushBack=char
            yield iri 

# Counts blank nodes to give a unique name to each of them
blankNodeCounter=0

def blankNodeName(subject, predicate=None):
    """ Generates a legible name for a blank node """
    global blankNodeCounter
    if ':' in subject:
        lastIndex=len(subject) - subject[::-1].index(':') - 1
        subject=subject[lastIndex+1:]+"_"
    elif predicate:
        subject=""
    if predicate and ':' in predicate:
        lastIndex=len(predicate) - predicate[::-1].index(':') - 1
        predicate=predicate[lastIndex+1:]
    else:
        predicate=""
    blankNodeCounter=blankNodeCounter+1
    return "_:"+subject+predicate+"_"+str(blankNodeCounter)
    
def triplesFromTerms(generator, givenSubject=None):
    """ Iterator over the triples of a term generator """
    while True:        
        term=next(generator)
        if not term or term==']':
            return
        if term=='.' or (term==';' and givenSubject):
            continue
        # If we're inside a [...]
        if givenSubject:
            subject=givenSubject
            if term!=',':
                predicate=term            
        # If we're in a normal statement     
        else:
            if term!=';' and term!=',':
                subject=term
            if term!=',':
                predicate=next(generator)
        if predicate=='a':
            predicate='rdf:type'
        # read the object
        object=next(generator)
        if not object:
            printError("File ended unexpectedly after", subject, predicate)
            return
        elif object in ['.',',',';']:
            printError("Unexpected",object,"after",subject,predicate)
            return
        elif object=='(':
            listNode=blankNodeName("list")
            previousListNode=None
            yield (subject, predicate, listNode)
            while True:
                term=next(generator)
                if not term:
                    printError("Unexpected end of file in collection (...)")
                    break  
                elif term==')':
                    break
                else:
                    if previousListNode:
                        yield (previousListNode, 'rdf:rest', listNode)
                    if term=='[':
                        term=blankNodeName("element")
                        yield (listNode, 'rdf:first', term)
                        yield from triplesFromTerms(generator, givenSubject=term)
                    else:    
                        yield (listNode, 'rdf:first', term)
                    previousListNode=listNode
                    listNode=blankNodeName("list")
            yield (previousListNode, 'rdf:rest', 'rdf:nil')
        elif object=='[':
            object=blankNodeName(subject, predicate)
            yield (subject, predicate, object)
            yield from triplesFromTerms(generator, givenSubject=object)
        else:
            yield (subject, predicate, object)

def turtleTriples(file, message=None):
    """ Iterator over the triples in a TTL file """
    return triplesFromTerms(termsAndSeparators(charsOfFile(file, message)))

##########################################################################
#             Graphs
##########################################################################

class Graph(object):
    """ A graph of triples """
    def __init__(self):
        self.index={}
        return
    def add(self, triple):
        (subject, predicate, obj) = triple
        if subject not in self.index:
            self.index[subject]={}
        m=self.index[subject]
        if predicate not in m:
            m[predicate]=set()
        m[predicate].add(obj)
    def remove(self, triple):
        (subject, predicate, obj) = triple
        if subject not in self.index:
            return
        m=self.index[subject]
        if predicate not in m:
            return
        m[predicate].remove(obj)
    def __contains__(self, triple):
        (subject, predicate, obj) = triple
        if subject not in self.index:
            return false
        m=self.index[subject]
        if predicate not in m:
            return false
        return obj in m[predicate]
    def loadTurtleFile(self, file, message=None):
        for triple in turtleTriples(file, message):
            self.add(triple)
    def objects(self, subject=None, predicate=None):
        # We create a copy here instead of using a generator
        # because the user loop may want to change the graph
        result=[]
        if subject and subject not in self.index:
            return result
        for s in ([subject] if subject else self.index):
            for p in ([predicate] if predicate else self.index[s]):
                if p in self.index[s]:
                    result.extend(self.index[s][p])
        return result
    def subjects(self, predicate=None, object=None):        
        if not predicate and not object:
            return [s for s in self.index]
        result=[]
        for s in self.index:            
            for p in ([predicate] if predicate else self.index[s]):                
                if p in self.index[s] and (not object or object in self.index[s][p]):
                    result.append(s)
                    break            
        return result
    def triplesWithPredicate(self, predicate):
        result=[]
        for subject in self.index:
            if predicate in self.index[subject]:
                for object in self.index[subject][predicate]:
                    result.append((subject, predicate, object))
        return result 
    def printToWriter(self, result):        
        for subject in self.index:
            if subject.startswith("_:list_"):
                continue
            result.write("\n")
            result.write(subject)
            result.write(' ')
            hasPreviousPred=False
            for predicate in self.index[subject]:
                if hasPreviousPred:
                    result.write(' ;\n\t')
                hasPreviousPred=True            
                result.write(predicate)
                result.write(' ')
                hasPrevious=False
                for obj in self.index[subject][predicate]:                    
                    if hasPrevious:
                        result.write(', ')
                    if obj.startswith("_:list_"):
                        result.write("(")
                        while True:
                            result.write(list(self.index[obj]['rdf:first'])[0])
                            obj=list(self.index[obj]['rdf:rest'])[0]
                            if obj=='rdf:nil':
                                break
                            result.write(" ")
                        result.write(")")
                    else:
                        result.write(obj)
                    hasPrevious=True
            result.write(' .\n')
    def printToFile(self, file):
        with open(file, "wt", encoding="utf-8") as out:
            for p in Prefixes.prefixes:
                out.write("@prefix "+p+": <"+Prefixes.prefixes[p]+"> .\n")
            self.printToWriter(out)
    def __str__(self):
        buffer=StringIO()
        buffer.write("# RDF Graph\n")
        self.printToWriter(buffer)
        return buffer.getvalue()
        
##########################################################################
#             Test
##########################################################################

if TEST and __name__ == '__main__':
    print("Test run of TurtleUtils...")
    graph=Graph()
    graph.loadTurtleFile("test-data/turtleUtils/shapes.ttl")
    graph.printToFile("test-data/turtleUtils/shapes-out.ttl")
    print("done")
    