"""
Utility functions for the creation of YAGO

(c) 2022 Fabian M. Suchanek
"""

from rdflib import URIRef, Graph, Namespace
import gzip
import gzip
import os

TEST=True

##########################################################################
#             Wikidata and schema.org URIs
##########################################################################

wikidataType = URIRef("http://www.wikidata.org/prop/direct/P31")

wikidataSubClassOf = URIRef("http://www.wikidata.org/prop/direct/P279")

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

prefixes = '''
@prefix bioschema: <http://bioschemas.org/> .
@prefix yago: <http://yago-knowledge.org/resource/> .
@prefix yagov: <http://yago-knowledge.org/value/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ontolex: <http://www.w3.org/ns/lemon/ontolex#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix wikibase: <http://wikiba.se/ontology#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix schema: <https://schema.org/> .
@prefix cc: <http://creativecommons.org/ns#> .
@prefix geo: <http://www.opengis.net/ont/geosparql#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix wd: <http://www.wikidata.org/entity/> .
@prefix data: <https://www.wikidata.org/wiki/Special:EntityData/> .
@prefix sh: <http://www.w3.org/ns/shacl#> . 
@prefix s: <http://www.wikidata.org/entity/statement/> .
@prefix ref: <http://www.wikidata.org/reference/> .
@prefix v: <http://www.wikidata.org/value/> .
@prefix wdt: <http://www.wikidata.org/prop/direct/> .
@prefix wdtn: <http://www.wikidata.org/prop/direct-normalized/> .
@prefix p: <http://www.wikidata.org/prop/> .
@prefix ps: <http://www.wikidata.org/prop/statement/> .
@prefix psv: <http://www.wikidata.org/prop/statement/value/> .
@prefix psn: <http://www.wikidata.org/prop/statement/value-normalized/> .
@prefix pq: <http://www.wikidata.org/prop/qualifier/> .
@prefix pqv: <http://www.wikidata.org/prop/qualifier/value/> .
@prefix pqn: <http://www.wikidata.org/prop/qualifier/value-normalized/> .
@prefix pr: <http://www.wikidata.org/prop/reference/> .
@prefix prv: <http://www.wikidata.org/prop/reference/value/> .
@prefix prn: <http://www.wikidata.org/prop/reference/value-normalized/> .
@prefix wdno: <http://www.wikidata.org/prop/novalue/> .
'''

EMPTY_GRAPH=Graph()
EMPTY_GRAPH.parse(data=prefixes, format="turtle")

##########################################################################
#             Parsing
##########################################################################

def getTopic(line):
    """Returns the subject of a compound statement in gthe form of one text line. Returns the Wikidata subject for meta statements (s:Q32~~~>ws:Q32)."""
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
    with (gzip.open(fileName, mode='rt', encoding='UTF-8') if fileName.endswith(".gz") else open(fileName, mode='rt', encoding='UTF-8')) as file:
        lines=""
        for line in file:
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
    print("  Parsing Wikidata...",end="", flush=True)
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
        result.parse(data=prefixes+statementsAboutTopic, format="n3")
        if len(result)>0:
            yield result
        statementsAboutTopic=compoundStatement
        currentTopic=topic
    print(" done")
    
def printGraph(graph, out=None):
    """Prints an RDF graph in a human-readable format"""
    if out:
        out.write(graph.serialize(format="turtle", encoding="utf-8"))
    else:
        print(str(graph.serialize(format="turtle", encoding="utf-8"), "utf-8"))

def compress(entity):
    """Compresses the URI prefix of Wikidata to "wd:" etc. """
    return entity.n3(EMPTY_GRAPH.namespace_manager)

def expandWikidataPrefix(entity):
    """Expands the URI prefix of Wikidata from "wd:" """
    if entity.startswith("wd:"):
       return "http://www.wikidata.org/entity/"+entity[3:]
    return entity    

##########################################################################
#             Test
##########################################################################

if TEST and __name__ == '__main__':
    print("Test run of utils...")
    with open("test-data/utils/test-output.ttl", "wb") as out:
        for entityFacts in readWikidataEntities("test-data/utils/test-input.ttl"):
            printGraph(entityFacts, out)
            for s,p,o in entityFacts:
                out.write(bytes(compress(s)+"\t"+compress(p)+"\t"+compress(o)+"\n","utf-8"))
    print("done")
