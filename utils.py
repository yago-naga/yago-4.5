"""
Utility functions for the creation of YAGO

(c) 2022 Fabian M. Suchanek
"""

from rdflib import URIRef, Graph, Namespace, Literal
from datetime import date
import gzip
import os
import sys

TEST=True

##########################################################################
#             Wikidata and schema.org URIs
##########################################################################

wikidataType = URIRef("http://www.wikidata.org/prop/direct/P31")

wikidataSubClassOf = URIRef("http://www.wikidata.org/prop/direct/P279")

wikidataParentTaxon = URIRef("http://www.wikidata.org/prop/direct/P171")

wikidataDuring = URIRef("http://www.wikidata.org/prop/qualifier/P585")

wikidataStart = URIRef("http://www.wikidata.org/prop/qualifier/P580")

wikidataEnd = URIRef("http://www.wikidata.org/prop/qualifier/P582")

owlDisjointWith = URIRef("http://www.w3.org/2002/07/owl#disjointWith")

schemaAbout = URIRef("https://schema.org/about")

schemaPage = URIRef("https://schema.org/mainEntityOfPage")

schemaThing = URIRef("https://schema.org/Thing")

fromClass = URIRef("http://yago-knowledge.org/schema#fromClass")

fromProperty = URIRef("http://yago-knowledge.org/schema#fromProperty")

shaclPath=URIRef("http://www.w3.org/ns/shacl#path")

shaclNode=URIRef("http://www.w3.org/ns/shacl#node")

shaclMaxCount=URIRef("http://www.w3.org/ns/shacl#maxCount")

shaclDatatype=URIRef("http://www.w3.org/ns/shacl#datatype")

shaclOr=URIRef("http://www.w3.org/ns/shacl#or")

shaclNodeKind=URIRef("http://www.w3.org/ns/shacl#nodeKind")

shaclPattern=URIRef("http://www.w3.org/ns/shacl#pattern")

shaclProperty=URIRef("http://www.w3.org/ns/shacl#property")

xsdYear = URIRef('http://www.w3.org/2001/XMLSchema#gYear')

prefixes = {
"bioschema": "http://bioschemas.org/",
"yago": "http://yago-knowledge.org/resource/",
"yagov": "http://yago-knowledge.org/value/",
"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
"xsd": "http://www.w3.org/2001/XMLSchema#",
"ontolex": "http://www.w3.org/ns/lemon/ontolex#",
"dct": "http://purl.org/dc/terms/",
"rdfs": "http://www.w3.org/2000/01/rdf-schema#",
"owl": "http://www.w3.org/2002/07/owl#",
"wikibase": "http://wikiba.se/ontology#",
"skos": "http://www.w3.org/2004/02/skos/core#",
"schema": "https://schema.org/",
"cc": "http://creativecommons.org/ns#",
"geo": "http://www.opengis.net/ont/geosparql#",
"prov": "http://www.w3.org/ns/prov#",
"wd": "http://www.wikidata.org/entity/",
"data": "https://www.wikidata.org/wiki/Special:EntityData/",
"sh": "http://www.w3.org/ns/shacl#",
"s": "http://www.wikidata.org/entity/statement/",
"ref": "http://www.wikidata.org/reference/",
"v": "http://www.wikidata.org/value/",
"wdt": "http://www.wikidata.org/prop/direct/",
"wdtn": "http://www.wikidata.org/prop/direct-normalized/",
"p": "http://www.wikidata.org/prop/",
"ps": "http://www.wikidata.org/prop/statement/",
"psv": "http://www.wikidata.org/prop/statement/value/",
"psn": "http://www.wikidata.org/prop/statement/value-normalized/",
"pq": "http://www.wikidata.org/prop/qualifier/",
"pqv": "http://www.wikidata.org/prop/qualifier/value/",
"pqn": "http://www.wikidata.org/prop/qualifier/value-normalized/",
"pr": "http://www.wikidata.org/prop/reference/",
"prv": "http://www.wikidata.org/prop/reference/value/",
"prn": "http://www.wikidata.org/prop/reference/value-normalized/",
"wdno": "http://www.wikidata.org/prop/novalue/",
"ys": "http://yago-knowledge.org/schema#" 
}

# For turtle parsing, see TODO further down
prefixesAsString="\n".join([ "@prefix "+p+": <"+prefixes[p]+"> ." for p in prefixes])

# For prefix resolution in compressPrefix
prefixesAsList= [ (s, prefixes[s]) for s in prefixes]
prefixesAsList.sort(key=(lambda t : t[1]), reverse=True)

##########################################################################
#             Reading lines of a file
##########################################################################

def linesOfFile(file, message="Parsing"):
    """ Iterator over the lines of a GZ or text file, with progress bar """
    print(message,"...", end="", flush=True)
    totalNumberOfDots=60-len(message)
    coveredSize=0
    printedDots=0
    fileSize=os.path.getsize(file)
    isGZ=file.endswith(".gz")
    if isGZ:
        fileSize*=20
    with (gzip.open(file, mode='rt', encoding='UTF-8') if isGZ else open(file, mode='rt', encoding='UTF-8')) as input:
        for line in input:
            coveredSize+=len(line)
            while coveredSize / fileSize * totalNumberOfDots > printedDots:
                print(".", end="", flush=True)
                printedDots+=1
            yield line
    while coveredSize / fileSize * totalNumberOfDots > printedDots:
        print(".", end="", flush=True)
        printedDots+=1
    print("done")

##########################################################################
#             TSV files
##########################################################################

# We use TSV files that can be parsed also as TTL files

def readTsvTuples(file, message="Parsing"):
    """ Iterates over the tuples in a TSV file"""
    for line in linesOfFile(file, message):
        if not line.startswith("#"):
            yield line.rstrip().split("\t")

class TsvFileWriter(object):
    """ To be used in a WITH...AS clause to write facts to TSV files"""
    def __init__(self, file_name):
        self.file_name = file_name
      
    def __enter__(self):
        self.file = open(self.file_name, "tw", encoding="utf=8")
        for p in prefixes:
            self.file.write("@prefix "+p+": <"+prefixes[p]+"> .\n")
        return self
        
    def write(self, *args):
        for i in range(0,len(args)-1):
            self.file.write(args[i])
            self.file.write("\t")
        self.file.write(args[-1])
        self.file.write("\n")
  
    def writeFact(self, subject,predicate, object):
        self.write(subject, predicate, object, ".")
        
    def __exit__(self, *exceptions):
        self.file.close()
        
##########################################################################
#             Parsing Wikidata
##########################################################################
        
def getTopic(line):
    """Returns the subject of a compound statement in the form of one text line. Returns the Wikidata subject for meta statements (s:Q32~~~>wd:Q32)."""
    if line.startswith("wd:Q"):
        return line[0:line.find(' ')]
    elif line.startswith("s:Q") or line.startswith("s:q"):
        return "wd:Q"+line[3:line.find('-')]
    elif "schema:about" in line:
        end=start=line.find("schema:about")+13
        while end<len(line) and line[end] in " \n\t":
            end+=1
        while end<len(line) and line[end] not in ",;. \n\t":
            end+=1
        return getTopic(line[start:end]+" ")
    return None

def statements(fileName):
    """Iterator over the compound statements in a TTL file. Returns a last dummy statement about Priscilla."""
    lines=""
    for line in linesOfFile(fileName, "  Parsing Wikidata"):
        line=line.strip()
        if line.startswith("@") or line.startswith("#") or len(line)==0:
            continue
        lines+=line
        if lines.endswith("."):
            yield lines
            lines=""        
    yield "wd:Q_Priscilla rdf:type schema:Person ."
    
def readWikidataEntities(fileName):    
    """Takes a TTL file as input, iterates over RDF graphs, each of which contains all facts about a topic (= a subject with its associated meta statements). """
    # ASSUMPTION: statements about one subject all follow each other the input file
    # ASSUMPTION: meta-statement identifiers start with the name of the subject
    # (as in s:Q31-7C0DCA8..., which is about wd:Q31)
    statementsAboutTopic=""
    currentTopic="Elvis"
    for compoundStatement in statements(fileName):        
        topic=getTopic(compoundStatement)
        if not topic:
           continue;
        if topic==currentTopic:
            statementsAboutTopic+=" "+compoundStatement
            continue            
        result = Graph()
        # TODO: It would be great if we could bind the prefixes
        # in the graph object instead of parsing them out of the prefixesAsString...
        result.parse(data=prefixesAsString+statementsAboutTopic, format="n3")
        if len(result)>0:
            yield result
        statementsAboutTopic=compoundStatement
        currentTopic=topic    
 
##########################################################################
#             Graph handling
##########################################################################
 
def printGraph(graph, out=None):
    """Prints an RDF graph in a human-readable format"""
    if out:
        out.write(graph.serialize(format="turtle", encoding="utf-8"))
    else:
        print(str(graph.serialize(format="turtle", encoding="utf-8"), "utf-8"))

def forcePrintGraph(graph):
    """Prints an RDF graph in TSV format even with bad characters"""
    for (s,p,o) in graph:
        sys.stdout.buffer.write((compressPrefix(s)+" "+compressPrefix(p)+" "+compressPrefix(o)+"\n").encode("utf8"))

def compressPrefix(entity):
    """ Compresses the URI prefix of Wikidata to "wd:" etc. Fixes Gregorian years to years. Returns the empty string for None. """
    if not entity:
        return ""
    if isinstance(entity, Literal) and entity.datatype==xsdYear and isinstance(entity.value, date) and entity.value.year:
        return('"'+str(entity.value.year)+'"^^xsd:gYear')
    for (s,l) in prefixesAsList:
        if entity.startswith(l):
            return s+":"+entity[len(l):]
    return entity.n3()

def expandPrefix(entity):
    """ Returns a URI for a CURIE """
    for p in prefixes:
        if entity.startswith(p+":"):
            return URIRef(prefixes[p]+entity[len(p)+1:])
    return URIRef(entity)
    
##########################################################################
#             Test
##########################################################################

if TEST and __name__ == '__main__':
    print("Test run of utils...")
    with TsvFileWriter("test-data/utils/test-output.ttl") as out:
        for entityFacts in readWikidataEntities("test-data/utils/test-input.ttl"):
            for (s,p,o) in entityFacts:
                out.writeFact(compressPrefix(s), compressPrefix(p), compressPrefix(o))
    print("done")
