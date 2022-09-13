"""
Reading Turtle files

(c) 2022 Fabian M. Suchanek
"""

from rdflib import URIRef, Graph, Namespace, Literal
from datetime import date
import gzip
import os
import sys
import TsvUtils

TEST=True

##########################################################################
#             Wikidata and schema.org URIs
##########################################################################

wikidataType = "wdt:P31"

wikidataSubClassOf = "wdt:P279"

wikidataParentTaxon = "wdt:P171"

wikidataDuring = "pq:P585"

wikidataStart = "pq:P580"

wikidataEnd = "pq:P582"

owlDisjointWith = "owl:disjointWith"

schemaAbout = "schema:about"

schemaPage = "schema:mainEntityOfPage"

schemaThing = "schema:Thing"

fromClass = "ys:fromClass"

fromProperty = "ys:fromProperty"

shaclPath="shacl:path"

shaclNode="shacl:node"

shaclMaxCount="shacl:maxCount"

shaclDatatype="shacl:datatype"

shaclOr="shacl:or"

shaclNodeKind="shacl:nodeKind"

shaclPattern="shacl:pattern"

shaclProperty="shacl:property"


##########################################################################
#             Parsing Turtle
##########################################################################

def printError(*args, **kwargs):
    """ Prints an error to StdErr """
    print(*args, file=sys.stderr, **kwargs)

def charsOfFile(file, message="Parsing"):
    """ Iterator over the chars of a GZ or text file, with progress bar """
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
            literal=literal.replace('\n','\\u000D').replace('\t','\\u0009')
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
        elif char in ['.',',',';','[',']']:
            # Separators
            yield char
        else:
            # Local names
            iri=""
            while not char.isspace() and char not in ['.',',',';','[',']','"',"'",'^','@']:
                iri=iri+char
                char=next(generator)
                if not char:
                    printError("Unexpected end of file in IRI",iri)
                    break
            pushBack=char
            yield iri 

blankNodeCounter=0
        
def triplesFromTerms(generator, givenSubject=None):
    """ Iterator over the triples of a term generator """
    while True:        
        term=next(generator)
        if not term or term==']':
            return
        if term=='.':
            continue
        if givenSubject:
            subject=givenSubject
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
        elif object=='[':
            object='_'+blankNodeCounter
            blankNodeCounter=blankNodeCounter+1
            yield (subject, predicate, object)
            triplesFromTerms(generator, givenSubject=object)
        else:
            yield (subject, predicate, object)

def triples(file, message="Parsing"):
    """ Iterator over the triples in a TTL file """
    return triplesFromTerms(termsAndSeparators(charsOfFile(file, message)))
        
##########################################################################
#             Test
##########################################################################

if TEST and __name__ == '__main__':
    print("Test run of utils...")
    with TsvUtils.TsvFileWriter("test-data/turtleUtils/test-output.tsv") as out:
        for triple in triples("test-data/turtleUtils/test-input.ttl"):
            out.writeFact(triple[0], triple[1], triple[2])
    print("done")
