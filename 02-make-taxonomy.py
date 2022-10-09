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

TEST=True
OUTPUT_FOLDER="test-data/02-make-taxonomy/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/02-make-taxonomy/00-wikidata.ttl" if TEST else "../wikidata.ttl"
SCHEMA_FILE = "test-data/02-make-taxonomy/01-yago-schema.ttl" if TEST else "yago-data/01-yago-schema.ttl"

###########################################################################
#           Booting
###########################################################################

import TurtleUtils
from TurtleUtils import Graph
from multiprocessing import Manager, Process, Array
import TsvUtils
import Prefixes
import sys
from os.path import exists
import os
from collections import defaultdict
import evaluator
from itertools import chain
                

###########################################################################
#           Loading the Wikidata taxonomy
###########################################################################

class wikidataVisitor():
    """ Will be called in parallel on each Wikidata entity graph, fills context[wikiTaxonomyDown] and context[wikidataClassesWithWikipediaPage]. """
    def __init__(self):
        self.wikidataTaxonomyDown={}
        self.wikidataClassesWithWikipediaPage=set()
    def visit(self,graph):    
        for s,p,o in graph:
            # We use the Wikidata property "ParentTaxon" as "rdfs:subclassOf",
            # because Wikidata sometimes uses only one of them
            if p==Prefixes.wikidataSubClassOf or p==Prefixes.wikidataParentTaxon:
                if o not in self.wikidataTaxonomyDown:
                    self.wikidataTaxonomyDown[o]=set()
                self.wikidataTaxonomyDown[o].add(s)
                for w in graph.subjects(Prefixes.schemaAbout, s):
                    if w.startswith("<https://en.wikipedia.org/wiki/"):
                        self.wikidataClassesWithWikipediaPage.add(s)
    def result(self):
        return(self.wikidataTaxonomyDown, self.wikidataClassesWithWikipediaPage)

###########################################################################
#           Creating the YAGO taxonomy
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
    # Due to loops, multiple inheritance, and inheritance between
    # class that have been mapped to YAGO, we might walk again
    # through a class that has been mapped to schema.org.
    # We have already done the subtree, so we can quit
    if yagoSchema.subjects(Prefixes.fromClass, wikidataClass):
        return
    elif wikidataClass in wikidataClassesWithWikipediaPage:
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
    for subClass in wikidataTaxonomyDown.get(wikidataClass,[]):    
        addSubClasses(lastGoodYagoClass, subClass, unmappedClassesWriter, treated, pathToRoot)
    pathToRoot.pop()


###########################################################################
#           Removing classes that subclass two disjoint top-level classes
###########################################################################
    
# stores for each class its disjoint toplevel classes
class2disjointTopLevelClasses=defaultdict(set)

def checkDisjoint(currentClass, superClass, disjointTopLevelClassesSoFar, disjointPairs):
    """ Dissolves the link between the currentClass and the superClass if this link causes a disjointness violation """
    if any( b for (currentClass,b) in disjointPairs) or any(b for (b, currentClass) in disjointPairs):
       class2disjointTopLevelClasses[currentClass].add(currentClass)
       disjointTopLevelClassesSoFar.add(currentClass)
    if any(a in class2disjointTopLevelClasses[currentClass] and b in disjointTopLevelClassesSoFar for (a,b) in disjointPairs):
        yagoTaxonomyDown[superClass].remove(currentClass)
        yagoTaxonomyUp[currentClass].remove(superClass)
    else:    
        class2disjointTopLevelClasses[currentClass].update(disjointTopLevelClassesSoFar)
        for subClass in set(yagoTaxonomyDown[currentClass]):
            checkDisjoint(subClass, currentClass, disjointTopLevelClassesSoFar, disjointPairs)
    disjointTopLevelClassesSoFar.discard(currentClass)
    
###########################################################################
#           Main
###########################################################################

if __name__ == '__main__':
    print("Creating YAGO taxonomy...")

    # Load YAGO schema
    yagoSchema = Graph()
    yagoSchema.loadTurtleFile(SCHEMA_FILE, "  Loading YAGO schema")
    disjointClasses=[ (c1, c2) for (c1, p, c2) in yagoSchema.triplesWithPredicate(Prefixes.owlDisjointWith) ]
    
    # Create YAGO taxonomy as two dictionaries,
    # mapping a subclass to its superclasses and vice versa
    yagoTaxonomyUp = defaultdict(set)
    yagoTaxonomyDown = defaultdict(set)
    for (s,p,o) in yagoSchema.triplesWithPredicate(Prefixes.rdfsSubClassOf):
        yagoTaxonomyUp[s].add(o)
        yagoTaxonomyDown[o].add(s)
        
    # Load Wikidata taxonomy
    results=TurtleUtils.visitWikidata(WIKIDATA_FILE, wikidataVisitor)
    # <results> is a list pairs of local results
    # We now merge them together in the global variables
    # <wikidataClassesWithWikipediaPage> and <wikidataTaxonomyDown>
    wikidataClassesWithWikipediaPage=set()
    wikidataTaxonomyDown=dict()
    for result in results:
        wikidataClassesWithWikipediaPage.update(result[1])
        for key in result[0]:
            if key not in wikidataTaxonomyDown:
                wikidataTaxonomyDown[key]=set()
            wikidataTaxonomyDown[key].update(result[0][key])
    
    # Write out non-YAGO classes
    print("  Writing non-YAGO classes...", end="", flush=True)
    with TsvUtils.TsvFileWriter(OUTPUT_FOLDER+"02-non-yago-classes.tsv") as unmappedClassesWriter:
        treated=set()
        for s,p,o in yagoSchema.triplesWithPredicate(Prefixes.fromClass):
            if s!=Prefixes.schemaThing:
                for subclass in wikidataTaxonomyDown.get(o,[]):
                    addSubClasses(s, subclass, unmappedClassesWriter, treated, [o])
    print("done")

    # Remove disjoint inconsistent classes
    print("  Removing disjoint-inconsistent subclass links...", end="", flush=True)
    checkDisjoint(Prefixes.schemaThing, None, set(), disjointClasses)
    print("done")

    # Write resulting taxonomy
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