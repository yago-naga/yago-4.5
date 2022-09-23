"""
Creates the YAGO 4 taxonomy from the Wikidata taxonomy and the YAGO 4 schema

(c) 2021 Fabian M. Suchanek

Call:
  python3 02-make-taxonomy.py

Input:
- 00-wikidata.ttl(.gz), the Wikidata file
- 01-yago-schema.ttl, the YAGO schema

Output:
- 02-yago-taxonomy.tsv, the YAGO lower level taxonomy in 
- 02-non-yago-classes.tsv, which maps classes that exist in Wikidata but not in YAGO to the nearest superclass in YAGO
    
Algorithm:
1) Start with top-level YAGO classes from the YAGO schema
2) For each YAGO top level class y that is mapped to a Wikidata class w,
   glue the entire subtree of w under y,
   - excluding bad classes
   - skipping over classes that do not have an English Wikipedia page
3) Remove a class and its descendants if it transitively subclasses two disjoint classes
"""

TEST=False
OUTPUT_FOLDER="test-data/02-make-taxonomy/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/02-make-taxonomy/00-wikidata.ttl" if TEST else "input-data/wikidata.ttl"
SCHEMA_FILE = "test-data/02-make-taxonomy/01-yago-schema.ttl" if TEST else "yago-data/01-yago-schema.ttl"

###########################################################################
#           Booting
###########################################################################

print("Creating YAGO taxonomy...")
print("  Importing...",end="", flush=True)
import TurtleUtils
from TurtleUtils import Graph
import threading
import TsvUtils
import Prefixes
import sys
from os.path import exists
from collections import defaultdict
import evaluator
from itertools import chain
print("done")

###########################################################################
#           Load YAGO top-level taxonomy and Wikidata taxonomy
###########################################################################

# Load YAGO schema
yagoSchema = Graph()
yagoSchema.loadTurtleFile(SCHEMA_FILE, "  Loading YAGO schema")

# YAGO taxonomy
# mapping a subclass to its superclasses and vice versa
yagoTaxonomyUp = defaultdict(set)
yagoTaxonomyDown = defaultdict(set)
for (s,p,o) in yagoSchema.triplesWithPredicate(Prefixes.rdfsSubClassOf):
    yagoTaxonomyUp[s].add(o)
    yagoTaxonomyDown[o].add(s)
    
# Load Wikidata taxonomy
wikidataTaxonomyDown=defaultdict(set)
lock=threading.Lock()
wikidataClassesWithWikipediaPage=set()

# Parallelized loading of the Wikidata taxonomy

def wikidataVisitor(graph, dummy):
    """ Will be called in parallel on each Wikidata entity graph, fills wikiTaxonomyDown """
    for s,p,o in graph:
        # We use the Wikidata property "ParentTaxon" as "rdfs:subclassOf",
        # because Wikidata sometimes uses only one of them
        if p==Prefixes.wikidataSubClassOf or p==Prefixes.wikidataParentTaxon:
            lock.acquire()
            wikidataTaxonomyDown[o].add(s)
            for w in graph.subjects(Prefixes.schemaAbout, s):
                if w.startswith("<https://en.wikipedia.org/wiki/"):
                    wikidataClassesWithWikipediaPage.add(s)
            lock.release()
    
TurtleUtils.visitWikidata(WIKIDATA_FILE, wikidataVisitor, None, [Prefixes.wikidataSubClassOf, Prefixes.wikidataParentTaxon, Prefixes.schemaAbout])

###########################################################################
#           Create YAGO taxonomy
###########################################################################

# Classes that will not be added to YAGO, and whose children won't be added either
badClasses = {
    "wd:Q17379835", # Wikimedia page outside the main knowledge tree
    "wd:Q17442446", # Wikimedia internal stuff
    "wd:Q4167410",  # disambiguation page
    "wd:Q13406463", # list article
    "wd:Q17524420", # aspect of history
    "wd:Q18340514"  # article about events in a specific year or time period
}

def addSubClasses(lastGoodYagoClass, wikidataClass, unmappedClassesWriter, treated, pathToRoot):
    """Adds the Wikidata classes to the YAGO taxonomy, excluding bad classes and classes without Wikipedia pages"""
    if wikidataClass in badClasses:
        return
    if wikidataClass in pathToRoot:
        return
    if wikidataClass in wikidataClassesWithWikipediaPage:
        yagoTaxonomyUp[wikidataClass].add(lastGoodYagoClass)
        yagoTaxonomyDown[lastGoodYagoClass].add(wikidataClass)
        lastGoodYagoClass=wikidataClass
    else:       
        unmappedClassesWriter.writeFact(wikidataClass,"rdfs:subClassOf",lastGoodYagoClass)
    # "Treated" serves to avoid adding the subclasses again in case of double inheritance
    if wikidataClass in treated:
        return
    treated.add(wikidataClass)
    pathToRoot.append(wikidataClass)
    for subClass in wikidataTaxonomyDown[wikidataClass]:    
        addSubClasses(lastGoodYagoClass, subClass, unmappedClassesWriter, treated, pathToRoot)
    pathToRoot.pop()

print("  Creating YAGO taxonomy...", end="", flush=True)
with TsvUtils.TsvFileWriter(OUTPUT_FOLDER+"02-non-yago-classes.tsv") as unmappedClassesWriter:
    treated=set()
    for s,p,o in yagoSchema.triplesWithPredicate(Prefixes.fromClass):
        if s!=Prefixes.schemaThing:
            for subclass in wikidataTaxonomyDown[o]:
                addSubClasses(s,subclass, unmappedClassesWriter,treated,[o])
print("done")

###########################################################################
#           Remove classes that subclass two disjoint top-level classes
###########################################################################

def disjoint(disjointTopLevelClass, cls):
    """TRUE if cls is a transitive subclass of a class that is disjoint with disjointTopLevelClass"""    
    return (disjointTopLevelClass, Prefixes.owlDisjointWith, cls) in yagoSchema \
        or any(disjoint(disjointTopLevelClass, superclass) for superclass in yagoTaxonomyUp[cls])

def removeClass(cls):
    """ Removes the class from the YAGO taxonomy """    
    for subClass in set(yagoTaxonomyDown[cls]):
        removeClass(subClass)
    yagoTaxonomyDown.pop(cls)
    for superclass in yagoTaxonomyUp[cls]:
        yagoTaxonomyDown[superclass].remove(cls)    
    yagoTaxonomyUp.pop(cls)
    
def checkDisjointness(disjointTopLevelClass, currentClass):
    """ Recursively top-down removes any classes that are disjoint with disjointTopLevelClass, starting with currentClass """   
    for subClass in set(yagoTaxonomyDown[currentClass]):
        for otherSuperclass in yagoTaxonomyUp[subClass]:
            if otherSuperclass==currentClass:
                continue
            if disjoint(disjointTopLevelClass, otherSuperclass):
                removeClass(subClass)
        checkDisjointness(disjointTopLevelClass, subClass)

print("  Removing disjoint-inconsistent classes...", end="", flush=True)
for s,p,o in yagoSchema.triplesWithPredicate(Prefixes.owlDisjointWith):
    checkDisjointness(s, Prefixes.schemaThing)
print("done")

###########################################################################
#           Serialize the result
###########################################################################

print("  Writing taxonomy...", end="", flush=True)
with TsvUtils.TsvFileWriter(OUTPUT_FOLDER+"02-yago-taxonomy.tsv") as taxonomyWriter:
    for cls in yagoTaxonomyUp:
        for superclass in yagoTaxonomyUp[cls]:
            taxonomyWriter.writeFact(cls, "rdfs:subClassOf", superclass)
print("done")
print("done")

if TEST:
    evaluator.compare(OUTPUT_FOLDER+"02-non-yago-classes.tsv")
    evaluator.compare(OUTPUT_FOLDER+"02-yago-taxonomy.tsv")