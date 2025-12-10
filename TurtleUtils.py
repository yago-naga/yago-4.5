"""
Reading Turtle files

CC-BY 2022 Fabian M. Suchanek
"""

import gzip
import os
import codecs
import re
import sys
from io import StringIO
import Prefixes
import TsvUtils
import multiprocessing

TEST=False

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
            literal=literal.replace('\n','\\n').replace('\t','\\t').replace('\r','').replace('\\"',"'").replace("\\u0022","'")
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
                    if (char>='A' and char<='Z') or (char>='a' and char<='z') or (char>='0' and char<='9') or char=='-':
                        language+=char
                        continue
                    pushBack=char                        
                    break
                if not language or len(language)>20 or len(language)<2 or ('-' in language and len(language[language.index('-'):])>9):
                    if TEST:
                        printError("Invalid literal language:", language)
                    yield('"'+literal+'"')  
                else:
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
                    printError("Unexpected end of file in URL","".join(uri))
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
    """ Generates a legible name for a blank node in the YS namespace """
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
    blankNodeCounter+=1
    return "ys:"+subject+predicate+"_"+str(blankNodeCounter)
    
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
    if message:
        print(message+"... ",end="",flush=True)
    with open(file,"rb") as reader:
        yield from triplesFromTerms(termsAndSeparators(charGenerator(byteGenerator(reader))), predicates)
    if message:
        print("done", flush=True)
    
##########################################################################
#             Graphs
##########################################################################

class Graph(object):
    """ A graph of triples """
    def __init__(self, hasInverse=True):
        self.index={}
        # Wikidata graphs are often about a main entity
        self.mainSubjectCache=None
        return
    def clear(self):
        self.index.clear()
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
        m[predicate].discard(obj)
        if len(m[predicate])==0:
            self.index[subject].pop(predicate)
            if len(self.index[subject])==0:
                self.index.pop(subject)
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
    def predicatesOf(self, subject):
        return self.index.get(subject,{})
    def objectsOf(self, subject, predicate):
        return self.index.get(subject,{}).get(predicate,set())
    def subjectsOf(self, predicate, obj):
        return list(s for s in self.index if predicate in self.index[s] and obj in self.index[s][predicate])
    def subjects(self):
        return self.index.keys()
    def triplesWithPredicate(self, *predicates):
        result=[]
        for subject in self.index:
            for predicate in predicates:
                if predicate in self.index[subject]:
                    for object in self.index[subject][predicate]:
                        result.append((subject, predicate, object))
        return result 
    def removeObjects(self, subject, predicate):
        if subject in self.index:
            if predicate in self.index[subject]:                    
                    self.index[subject][predicate].clear()
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
                        result.write(" ".join(self.getList(obj)))
                        result.write(")")
                    else:
                        result.write(obj)
                    hasPrevious=True
            result.write(' .\n')
    def printToFile(self, file):
        with open(file, "wt", encoding="utf-8") as out:
            for p in Prefixes.yagoPrefixes:
                out.write("@prefix "+p+": <"+Prefixes.prefixes[p]+"> .\n")
            self.printToWriter(out)
    def __str__(self):
        buffer=StringIO()
        buffer.write("# RDF Graph\n")
        self.printToWriter(buffer)
        return buffer.getvalue()
    def mainSubject(self):
        if self.mainSubjectCache:
            return self.mainSubjectCache
        for key in self.index:
            if not key.startswith("s:"):
                self.mainSubjectCache=key
                return key
        return None
    def __len__(self):
        return len(self.index)

# Regex for literals
literalRegex=re.compile('"([^"]*)"(@([a-z-]+))?(\\^\\^(.*))?')

# Regex for int values
intRegex=re.compile('[+-]?[0-9.]+')

def splitLiteral(term):
    """ Returns String value, int value, language, and datatype of a term (or None, None, None, None). No good backslash handling """
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

def isEntity(term):
    """ TRUE if the entity is of the form abc:def"""
    return re.match("[a-z]+:.*",term)

def isLiteral(term):
    """ TRUE for literals"""
    return term.startswith('"')
    
def isDate(obj):
    """ TRUE if valid date object """
    if obj is None:
        return False
    string, intValue, language, dataType=splitLiteral(obj)
    return string and dataType and (dataType==Prefixes.xsdDateTime or dataType==Prefixes.xsdDate) 

def isEntityWithPrefix(term, permitted_namespaces = ["geo:", "rdfs:", "yago:", "xsd:", "schema:", "rdf:", "wd:"]):
    """ TRUE if the term is an entity of that namespace """
    return any(term.startswith(s) for s in permitted_namespaces )

def isRegex(pattern):
    """ TRUE for regexes"""
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False
    
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

def entitiesFromTriples(tripleIterator):
    """ Yields graphs about entities from the triples """
    graph=Graph()
    currentSubject="Elvis"
    for triple in tripleIterator:
        newSubject=about(triple)
        if not newSubject: 
            continue
        if newSubject!=currentSubject:
            if len(graph):
                graph.mainSubjectCache=currentSubject
                yield graph
                graph=Graph()
            currentSubject=newSubject
        graph.add(triple)
    if len(graph):
        yield graph

# Buffer sizes  
kilo=1024
mega=1024*kilo
giga=1024*mega

def visitWikidataEntities(args):
    """ Visits the Wikidata entities. The arguments are
              file, visitor, portion, size
    The visitor is called on all Wikidata entities in the file,
    starting from portion*size """
    # The arguments are packed in a single argument
    # so that we can call Pool.map() with this function.
    # So we unpack them.
    file, visitor, portion, size = args
    print("    Starting Wikidata reader",portion+1)
    with open(file,"rb", buffering=1*mega) as wikidataReader:
        wikidataReader.seek(portion*size)
        # Seek to next Wikidata item
        line=b"NONE"
        for line in wikidataReader:
            if line.rstrip().endswith(b"a wikibase:Item ."):
                break
        print("    Running Wikidata reader",portion+1,"at",wikidataReader.tell(),"with \"",line.rstrip().decode("utf-8"),'"', flush=True)        
        for graph in entitiesFromTriples(triplesFromTerms(termsAndSeparators(charGenerator(byteGenerator(wikidataReader))))):
            visitor.visit(graph)
            if wikidataReader.tell()>portion*size+size:
                break            
    print("    Finished Wikidata reader",portion+1, flush=True)        
    return visitor.result()

def visitWikidata(file, visitor, numThreads=90):
    """ Runs numThreads parallel threads that each visit a portion of Wikidata with the visitor """
    fileSize=os.path.getsize(file)
    if numThreads>fileSize/10000000:
        numThreads=int(fileSize/10000000)+1
    print("  Running",numThreads,"Wikidata readers", flush=True)
    portionSize=int(fileSize/numThreads)
    with multiprocessing.get_context("spawn").Pool(processes=numThreads) as pool:
        result=pool.map(visitWikidataEntities, ((file, visitor(i), i, portionSize,) for i in range(0,numThreads)), 1)
    print("  done", flush=True)
    return(result)

def tsvEntities(file, message=None):
    """ Iterates over the entity graphs in a TSV file """
    previousEntity="Elvis"
    graph=Graph()
    for split in TsvUtils.tsvTuples(file, message):
        if split[0]!=previousEntity:
            if graph:
                yield graph
            graph=Graph()
            previousEntity=split[0]
        graph.add((split[0], split[1], split[2]))
    if graph:
        yield graph
        
##########################################################################
#             Test
##########################################################################

def checkTerm(term):
    """ TRUE if the term is a constant, a literal, or has a prefix """
    if term==None or len(term)<1:
        return False
    return term.startswith('"') or term.startswith('<http') or term=="true" or term=="false" or term.find(":")!=-1 or term[0] in "0123456789-+"
    
def printWD(graph, out):
    """ A Wikidata visitor that just prints the graph """
    out.lock.acquire()
    out.write('#####################################\n')
    graph.printToWriter(out)
    out.lock.release()

def compareIds(wikidataFile, idFile):
    """ Verifies that every id in idFile appears in the parsing of wikidataFile """
    with open(idFile,'rt',encoding='utf-8') as idReader:
        with open(wikidataFile,"rb") as wikidataReader:        
            for graph in entitiesFromTriples(triplesFromTerms(termsAndSeparators(charGenerator(byteGenerator(wikidataReader))))):
                if "wikibase:Item" not in graph.objects():
                    continue
                subjects=graph.subjects()
                nextId=next(idReader,"EOF ").split(' ')[0]
                if nextId not in subjects:
                    print("Next id is",nextId,"but subjects are",subjects)
                    break
                print(nextId, "OK")
        
if TEST and __name__ == '__main__':
    with open("test-data/turtleUtils/schema-org.tsv", "tw", encoding="UTF-8") as f:
        for triple in triplesFromTurtleFile("test-data/turtleUtils/schema-org.ttl"):
            f.write(triple[0]+"\t"+triple[1]+"\t"+triple[2]+"\t.\n")