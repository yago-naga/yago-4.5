"""
Creates the YAGO 4 taxonomy from the Wikidata taxonomy and the YAGO 4 schema

CC-BY 2021 Fabian M. Suchanek

Call:
  python3 02-make-taxonomy.py

Input:
- 00-wikidata.ttl(.gz), the Wikidata file
- 01-yago-final-schema.ttl, the YAGO schema

Output:
- 02-yago-taxonomy-to-rename.tsv, the YAGO lower level taxonomy
    
Algorithm:
1) Start with top-level YAGO classes from the YAGO schema
2) For each YAGO top level class y that is mapped to a Wikidata class w,
   glue the entire subtree of w under y
3) Remove a class and its descendants if it transitively subclasses two disjoint classes
"""

TEST=False
OUTPUT_FOLDER="test-data/02-make-taxonomy/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/02-make-taxonomy/00-wikidata.ttl" if TEST else "../wikidata.ttl"
SCHEMA_FILE = "test-data/02-make-taxonomy/01-yago-final-schema.ttl" if TEST else "yago-data/01-yago-final-schema.ttl"

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


# Properties that indicate that the entity is an instance for YAGO
instanceIndicators= {
  "wdt:P171", # parent taxon -> instance of taxon
  "wdt:P176", # manufacturer -> instance of Product
  "wdt:P178"  # developer -> instance of Product
}

class wikidataVisitor(object):
    """ Will be called in parallel on each Wikidata entity graph, fills context[wikiTaxonomyDown]. """
    def __init__(self, id):
        self.wikidataTaxonomyDown={}
    def visit(self,graph): 
        predicates=graph.predicates()
        if not predicates.isdisjoint(instanceIndicators):
            return
        if not Prefixes.rdfsLabel in predicates:
            return
        for s,p,o in graph:            
            if p==Prefixes.wikidataSubClassOf or p==Prefixes.wikidataAnalogousClass:
                if o not in self.wikidataTaxonomyDown:
                    self.wikidataTaxonomyDown[o]=set()
                self.wikidataTaxonomyDown[o].add(s)
    def result(self):
        return(self.wikidataTaxonomyDown)

###########################################################################
#           Creating the YAGO taxonomy
###########################################################################

# Classes that will not be added to YAGO, and whose children won't be added either
badClasses = {
    "wd:Q17379835", # Wikimedia page outside the main knowledge tree
    "wd:Q17442446", # Wikimedia internal stuff
    "wd:Q15474042", # same
    "wd:Q111279923",# same 
    "wd:Q4167410",  # disambiguation page
    "wd:Q13406463", # list article
    "wd:Q17524420", # aspect of history
    "wd:Q18340514", # article about events in a specific year or time period
    "wd:Q24017414", # second-order class
    "wd:Q12335479", # templates
    "wd:Q12139612", # Lists
    "wd:Q80096233", # Lists
    "wd:Q13406463", # Lists
    "wd:Q88392887", # scholarly articles, tweets, etc.
    "wd:Q591041",   # same
    "wd:Q13442814", # same
    "wd:Q3523102",  # same
    "wd:Q115668308",# Release    
    "wd:Q618123",   # geographical feature
    "wd:Q13226383", # facility
    "wd:Q2221906",  # geographical location
    "wd:Q15642541", # human-geographic territorial entity    
    "wd:Q4835091",  # territory
    "wd:Q4026292",  # Action
    "wd:Q67518978", # Occurrent
    "wd:Q2545446",  # Graphemes
    "wd:Q32483",    # Characters
    "wd:Q3241972",  # Characters
    "wd:Q29654788", # Unicode characters
    "wd:Q11953984", # Linguistic units, words etc
    "wd:Q11563",    # Numbers,
    "wd:Q192581",   # Job -> causes problem because instances of "lawyer" become instances of "job" and thus of "economic activity"
    "wd:Q12737077", # Occupation (dito)
    "wd:Q28640",    # Profession (dito)
    "wd:Q4164871"   # Role (dito)
}

def subClassesInclude(superClass, potentialSubClass):
    """TRUE if the subclasses of superClass include subClass"""
    if superClass==potentialSubClass:
        return True
    for subClass in yagoTaxonomyDown.get(superClass,[]):    
        if subClassesInclude(subClass, potentialSubClass):
            return True
    return False

loopCounter=0
    
def addSubClass(superClass, subClass):
    """Adds the Wikidata classes to the YAGO taxonomy, excluding bad classes"""
    global loopCounter
    if subClass in badClasses:
        return
    if subClassesInclude(subClass, superClass):
        loopCounter+=1
        return
    # Both a class and its subclass might be mapped to YAGO.
    # So don't make a copy of the tree
    if yagoSchema.subjects(Prefixes.fromClass, subClass):
        return
    yagoTaxonomyUp[subClass].add(superClass)
    yagoTaxonomyDown[superClass].add(subClass)
    # Avoid adding the subclasses again in case of double inheritance
    if subClass in yagoTaxonomyDown:
        return
    for subClass2 in wikidataTaxonomyDown.get(subClass,[]):    
        addSubClass(subClass, subClass2)        
    

###########################################################################
#           Removing shortcuts
###########################################################################

def removeShortcutParentsOf(startClass, currentClass):
    """ Removes direct superclasses of startClass that are equal to currentClass or its super-classes """
    if currentClass in yagoTaxonomyUp.get(startClass,[]):
        yagoTaxonomyUp[startClass].remove(currentClass)
        yagoTaxonomyDown[currentClass].remove(startClass)
        if len(yagoTaxonomyUp[startClass])==1:
            return        
    for s in yagoTaxonomyUp.get(currentClass,[]):
        removeShortcutParentsOf(startClass, s)
        
def removeShortcuts():
    """ Removes all shortcut links in the YAGO taxonomy """
    for c in list(yagoTaxonomyUp):
        if len(yagoTaxonomyUp.get(c,[]))>1:
            for s in list(yagoTaxonomyUp.get(c,[])):
                for ss in yagoTaxonomyUp.get(s,[]):
                    removeShortcutParentsOf(c, ss)
            
            
###########################################################################
#           Removing classes that subclass two disjoint top-level classes
###########################################################################
    
# stores for each class its disjoint toplevel classes
class2disjointTopLevelClasses=defaultdict(set)

def checkDisjoint(currentClass, superClass, disjointTopLevelClassesSoFar, disjointPairs):
    """ Dissolves the link between the currentClass and the superClass if this link causes a disjointness violation """
    if any( b for (a,b) in disjointPairs if a==currentClass) or any(b for (b, a) in disjointPairs if a==currentClass):               
       disjointTopLevelClassesSoFar.add(currentClass)
    if any(a in class2disjointTopLevelClasses[currentClass] and b in disjointTopLevelClassesSoFar for (a,b) in disjointPairs) \
       or any(a in class2disjointTopLevelClasses[currentClass] and b in disjointTopLevelClassesSoFar for (b,a) in disjointPairs):
        yagoTaxonomyDown[superClass].remove(currentClass)
        yagoTaxonomyUp[currentClass].remove(superClass)
    else:    
        class2disjointTopLevelClasses[currentClass].update(disjointTopLevelClassesSoFar)
        # Make this deterministic
        subclasses=list(yagoTaxonomyDown[currentClass])
        subclasses.sort()
        for subClass in subclasses:
            checkDisjoint(subClass, currentClass, disjointTopLevelClassesSoFar, disjointPairs)
    disjointTopLevelClassesSoFar.discard(currentClass)
    
###########################################################################
#           Main
###########################################################################

if __name__ == '__main__':
    with TsvUtils.Timer("Step 02: Creating YAGO taxonomy"):
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
        # <results> is a list of taxonomies
        # We now merge them together in the global variable <wikidataTaxonomyDown>
        wikidataTaxonomyDown=dict()
        for result in results:
            for key in result:
                if key not in wikidataTaxonomyDown:
                    wikidataTaxonomyDown[key]=set()
                wikidataTaxonomyDown[key].update(result[key])
        print("  Info: Total number of Wikidata classes and taxonomic links:", len(wikidataTaxonomyDown), " and ", sum(len(wikidataTaxonomyDown[s]) for s in wikidataTaxonomyDown))
                
        # Now we merge the Wikidata taxonomy into the YAGO taxonomy
        for s,p,o in yagoSchema.triplesWithPredicate(Prefixes.fromClass):
                if s!=Prefixes.schemaThing:
                    for subclass in wikidataTaxonomyDown.get(o,[]):
                        addSubClass(s, subclass)

        print("  Info: Loops removed:", loopCounter)
        print("  Info: YAGO classes and links (= only those Wikidata classes that are below declared high-level classes) before cleaning:",len(yagoTaxonomyUp), " and ", sum(len(yagoTaxonomyUp[s]) for s in yagoTaxonomyUp))
        
        # Remove shortcuts
        print("  Removing shortcut links...", end="", flush=True)
        removeShortcuts()
        print("done")
        print("  Info: YAGO classes and links after shortcut removal:",len(yagoTaxonomyUp), " and ", sum(len(yagoTaxonomyUp[s]) for s in yagoTaxonomyUp))
                        
        # Remove disjoint inconsistent classes
        print("  Removing disjoint-inconsistent subclass links...", end="", flush=True)
        checkDisjoint(Prefixes.schemaThing, None, set(), disjointClasses)
        print("done")
        print("  Info: Total number of YAGO classes and taxonomic links, after removing disjoints, before removing empty classes:",len(yagoTaxonomyUp), " and ", sum(len(yagoTaxonomyUp[s]) for s in yagoTaxonomyUp))
        
        # Write resulting taxonomy
        print("  Writing taxonomy...", end="", flush=True)
        with TsvUtils.TsvFileWriter(OUTPUT_FOLDER+"02-yago-taxonomy-to-rename.tsv") as taxonomyWriter:
            for cls in yagoTaxonomyUp:
                for superclass in yagoTaxonomyUp[cls]:
                    taxonomyWriter.writeFact(cls, "rdfs:subClassOf", superclass)
        print("done")

    if TEST:
        evaluator.compare(OUTPUT_FOLDER+"02-yago-taxonomy-to-rename.tsv")