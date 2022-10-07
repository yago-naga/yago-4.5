"""
Reading Turtle files

(c) 2022 Fabian M. Suchanek
"""

import gzip
import os
import codecs
import re
import sys
from io import StringIO
import Prefixes
from multiprocessing import Process, Pool

TEST=True

##########################################################################
#             Parsing Turtle
##########################################################################

def printError(*args, **kwargs):
    """ Prints an error to StdErr """
    print(*args, file=sys.stderr, **kwargs)
    
def termsAndSeparators(generator):
    """ Iterator over the terms of char reader """
    pushBack=None
    while True:
        # Scroll to next term
        while True:
            char=pushBack if pushBack else next(generator, None)
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
                    char=next(generator, None)
            elif char.isspace():
                # whitespace
                pass
            else:
                break
                
        # Strings
        if char=='"':
            secondChar=next(generator, None)
            thirdChar=next(generator, None)
            if secondChar=='"' and thirdChar=='"':
                # long string quote
                literal=""
                while True:
                    char=next(generator, None)
                    if char:
                        literal=literal+char
                    else:
                        printError("Unexpected end of file in literal",literal)
                        literal=literal+'"""'
                        break
                    if literal.endswith('"""'):
                        break
                literal=literal[:-3]
                char=None
            else:
                # Short string quote
                if secondChar=='"':
                    literal=''
                    char=thirdChar
                elif thirdChar=='"' and secondChar!='\\':
                    literal=secondChar
                    char=None
                else:    
                    literal=[secondChar,thirdChar]
                    if thirdChar=='\\' and secondChar!='\\':
                        literal+=next(generator, ' ')
                    while True:
                        char=next(generator, None)
                        if not char:
                            printError("Unexpected end of file in literal",literal)
                            break
                        elif char=='\\':
                            literal+=char
                            literal+=next(generator, ' ')
                            continue
                        elif char=='"':
                            break
                        literal+=char
                    char=None
                    literal="".join(literal)
            # Make all literals simple literals without line breaks and quotes
            literal=literal.replace('\n','\\n').replace('\t','\\t').replace('\r','').replace('\\"','\\u0022')
            if not char:
                char=next(generator, None)
            if char=='^':
                # Datatypes
                next(generator, None)
                datatype=''
                while True:
                    char=next(generator, None)
                    if not char:
                        printError("Unexpected end of file in datatype of",literal)
                        break
                    if len(datatype)>0 and datatype[0]!='<' and char!=':' and (char<'A' or char>'z'):
                        pushBack=char
                        break
                    datatype=datatype+char
                    if datatype.startswith('<') and datatype.endswith('>'):
                        break
                if not datatype or len(datatype)<3:
                    printError("Invalid literal datatype:", datatype)
                yield('"'+literal+'"^^'+datatype)
            elif char=='@':
                # Languages
                language=""
                while True:
                    char=next(generator, None)
                    if not char:
                        printError("Unexpected end of file in language of",literal)
                        break
                    if char=='-' or (char>='A' and char<='Z') or (char>='a' and char<='z') or (char>='0' and char<='9'):
                        language=language+char
                        continue
                    break
                if not language or len(language)>20 or len(language)<2:
                    printError("Invalid literal language:", language)
                pushBack=char
                yield('"'+literal+'"@'+language)
            else:
                pushBack=char
                yield('"'+literal+'"')
        elif char=='<':
            # URIs
            uri=[]
            while char!='>':
                uri+=char
                char=next(generator, None)
                if not char:
                    printError("Unexpected end of file in URL",uri)
                    break
            uri+='>'
            yield "".join(uri)
        elif char in ['.',',',';','[',']','(',')']:
            # Separators
            yield char
        else:
            # Local names
            iri=[]
            while not char.isspace() and char not in ['.',',',';','[',']','"',"'",'^','@','(',')']:
                iri+=char
                char=next(generator, None)
                if not char:
                    printError("Unexpected end of file in IRI",iri)
                    break
            pushBack=char
            yield "".join(iri)
    
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
    
def triplesFromTerms(generator, predicates=None, givenSubject=None):
    """ Iterator over the triples of a term generator """
    while True:        
        term=next(generator, None)
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
                predicate=next(generator, None)
        if predicate=='a':
            predicate='rdf:type'
        # read the object
        object=next(generator, None)
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
                term=next(generator, None)
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
                        yield from triplesFromTerms(generator, predicates, givenSubject=term)
                    else:    
                        yield (listNode, 'rdf:first', term)
                    previousListNode=listNode
                    listNode=blankNodeName("list")
            yield (previousListNode, 'rdf:rest', 'rdf:nil')
        elif object=='[':
            object=blankNodeName(subject, predicate)
            yield (subject, predicate, object)
            yield from triplesFromTerms(generator, predicates, givenSubject=object)
        else:
            if (not predicates) or (predicate in predicates):
                yield (subject, predicate, object)

##########################################################################
#             Reading files
##########################################################################

def byteGenerator(byteReader):
    """ Generates bytes from the reader """
    while True:
        b=byteReader.read(1)
        if b:
            yield b
        else:
            break

def charGenerator(byteGenerator):
    """ Generates chars from bytes """
    return codecs.iterdecode(byteGenerator, "utf-8")

def triplesFromTurtleFile(file, message=None, predicates=None):
    """ Iterator over the triples in a TTL file """
    print((message if message else "  Parsing "+file)+"... ",end="", flush=True)
    with open(file,"rb") as reader:
        yield from triplesFromTerms(termsAndSeparators(charGenerator(byteGenerator(reader))), predicates)
    print("done", flush=True)
    
##########################################################################
#             Graphs
##########################################################################

class Graph(object):
    """ A graph of triples """
    def __init__(self, hasInverse=True):
        self.index={}
        # We add an inverse graph to query more easily for subjects of a given predicate and object
        self.inverseGraph=Graph(False) if hasInverse else None
        return
    def add(self, triple):
        (subject, predicate, obj) = triple
        if subject not in self.index:
            self.index[subject]={}
        m=self.index[subject]
        if predicate not in m:
            m[predicate]=set()
        m[predicate].add(obj)
        if self.inverseGraph!=None:
            self.inverseGraph.add((obj,predicate,subject))
    def remove(self, triple):
        (subject, predicate, obj) = triple
        if subject not in self.index:
            return
        m=self.index[subject]
        if predicate not in m:
            return
        m[predicate].remove(obj)
        if len(m[predicate])==0:
            self.index[subject].pop(predicate)
            if len(self.index[subject])==0:
                self.index.pop(subject)
        if self.inverseGraph!=None:
            self.inverseGraph.remove((obj,predicate,subject))        
    def __contains__(self, triple):
        (subject, predicate, obj) = triple
        if subject not in self.index:
            return False
        m=self.index[subject]
        if predicate not in m:
            return False
        return obj in m[predicate]
    def __iter__(self):
        for s in self.index:
            for p in self.index[s]:
                for o in self.index[s][p]:
                    yield (s,p,o)
    def loadTurtleFile(self, file, message=None):
        for triple in triplesFromTurtleFile(file, message):
            self.add(triple)
    def getList(self, listStart):
        """ Returns the elements of an RDF list"""
        result=[]
        while listStart and listStart!='rdf:nil':
            result.extend(self.index[listStart].get('rdf:first',[]))
            if 'rdf:rest' not in self.index[listStart]:
                break
            listStart=list(self.index[listStart]['rdf:rest'])[0]            
        return result
    def predicates(self):
        result=set()
        for s in self.index:
            for p in self.index[s]:
                result.add(p)
        return result
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
        if self.inverseGraph!=None:
            return self.inverseGraph.objects(subject=object, predicate=predicate)
        else:
            raise Exception("subjects() cannot be called on inverse graph")
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
                        result.write(", ".join(self.getList(obj)))
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
    def __len__(self):
        return len(self.index)

# Regex for literals
literalRegex=re.compile('"([^"]*)"(@([a-z-]+))?(\\^\\^(.*))?')

# Regex for int values
intRegex=re.compile('[+-]?[0-9.]+')

def splitLiteral(term):
    """ Returns String value, int value, language, and datatype of a term (or None, None, None, None)"""
    match=re.match(intRegex, term)
    if match:
        try:
            intValue=int(term)
        except:
            return(None, None, None, None)
        return(term, intValue, None, 'xsd:integer')
    # This works only because our Turtle Parser replaces all quotes in strings by \u0022!
    match=re.match(literalRegex, term)
    if not match:
        return(None, None, None, None)
    try:
        intValue=int(match.group(1))
    except:
        intValue=None
    return (match.group(1), intValue, match.group(3), match.group(5))
    
##########################################################################
#             Reading Wikidata entities
##########################################################################

def about(triple):
    """ Returns the Wikidata subject of the triple"""
    s,p,o=triple
    if p=="schema:about":
        s=o
    if s.startswith("wd:Q"): 
        return s
    if s.startswith("s:Q") or s.startswith("s:q"):
        return "wd:Q"+s[3:s.index('-')]
    return None

# Buffer sizes  
kilo=1024
mega=1024*kilo
giga=1024*mega

def visitWikidataEntities(args):
    """ Visits the Wikidata entities starting from portion*size """    
    file, visitor, portion, size = args
    print("    Initializing Wikidata reader",portion+1)
    percentagePrinted=0
    with open(file,"rb", buffering=1*giga) as wikidataReader:
        wikidataReader.seek(portion*size)
        for line in wikidataReader:
            if line.rstrip().endswith(b"a wikibase:Item ."):
                break
        print("    Running Wikidata reader",portion+1,"at",wikidataReader.tell(),"with \"",line.rstrip().decode("utf-8"),'"', flush=True)        
        graph=Graph()
        currentSubject="Elvis"
        context=dict()
        for triple in triplesFromTerms(termsAndSeparators(charGenerator(byteGenerator(wikidataReader)))):
            newSubject=about(triple)
            if not newSubject: 
                continue
            if newSubject!=currentSubject:
                if len(graph):
                    while percentagePrinted<(wikidataReader.tell()-portion*size)/size*10:
                        percentagePrinted+=1
                        print("    Wikidata reader",portion+1,"is at",percentagePrinted*10,"%", flush=True)
                    visitor(graph, context)
                    graph=Graph()
                currentSubject=newSubject
                if wikidataReader.tell()>portion*size+size:
                    print("    Wikidata reader",portion+1,"finishes before",currentSubject, flush=True)
                    break
            graph.add(triple)
    if len(graph):
        visitor(graph, context)     
    print("    Finished Wikidata reader",portion+1, flush=True)        
    return context

def visitWikidata(file, visitor, numThreads=90):
    """ Runs numThreads parallel threads that each visit a portion of Wikidata with the visitor"""
    fileSize=os.path.getsize(file)
    if numThreads>fileSize/10000000:
        numThreads=int(fileSize/10000000)+1
    print("  Running",numThreads,"Wikidata readers", flush=True)
    portionSize=int(fileSize/numThreads)
    with Pool(processes=numThreads) as pool:
        result=pool.map(visitWikidataEntities, ((file, visitor, i, portionSize,) for i in range(0,numThreads)), 1)
    print("  done", flush=True)
    return(result)
    
##########################################################################
#             Test
##########################################################################

def printWD(graph, out):
    """ A Wikidata visitor that just prints the graph """
    out.lock.acquire()
    out.write('#####################################\n')
    graph.printToWriter(out)
    out.lock.release()
    
if TEST and __name__ == '__main__':
    with open('test-out.ttl','wt',encoding='utf-8') as out:
        out.lock=threading.Lock()
        visitWikidata('input-data/wikidata.ttl', printWD, out,None,2)            