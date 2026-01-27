"""
Creates the YAGO 4.5 taxonomy from the Wikidata taxonomy and the YAGO 4.5 schema

CC-BY 2021-2025 Fabian M. Suchanek

Call:
  python 02-make-taxonomy.py

Input:
- 00-wikidata.ttl(.gz), the Wikidata file
- 01-yago-final-schema.ttl, the YAGO schema

Output:
- 02-yago-taxonomy-to-rename.tsv, the YAGO lower level taxonomy
    
Algorithm:
1) Start with top-level YAGO classes from the YAGO schema
2) For each YAGO top level class y that is mapped to a Wikidata class w,
   glue the entire subtree of w under y, removing disjoint classes,
   loops, and shortcuts
"""

###########################################################################
#           Booting
###########################################################################

import TurtleUtils
import TsvUtils
import Prefixes
import Schema
import sys
import os
from collections import defaultdict
import Evaluator
     
TEST=len(sys.argv)>1 and sys.argv[1]=="--test"     

OUTPUT_FOLDER="test-data/02-make-taxonomy/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/02-make-taxonomy/00-wikidata.ttl" if TEST else "../wikidata.ttl"
SCHEMA_FILE = "yago-data/01-yago-final-schema.ttl"

###########################################################################
#           Loading the Wikidata taxonomy
###########################################################################


# Properties that indicate that the entity is an instance for YAGO
instanceIndicators = {
    "wdt:P171",  # parent taxon -> instance of taxon
    "wdt:P176",  # manufacturer -> instance of Product
    "wdt:P178"   # developer -> instance of Product
}

class WikidataVisitor:
    """ Will be called in parallel on each Wikidata entity graph, creates a downward pointing Wikidata taxonomy. """
    def __init__(self, workerId):
        self.wikidataTaxonomyDown = {}
    
    def visit(self, graph): 
        predicates = graph.predicates()

        # Ignore classes without labels
        if Prefixes.rdfsLabel not in predicates:
            return
        # Ignore non-classes
        if Prefixes.wikidataSubClassOf not in predicates and Prefixes.wikidataAnalogousClass not in predicates:
            return        
        # If we're handling an instance, quit (use set intersection for efficiency)
        if predicates & instanceIndicators:
            return
        for subject, predicate, obj in graph:            
            if predicate == Prefixes.wikidataSubClassOf or predicate == Prefixes.wikidataAnalogousClass:
                if obj not in self.wikidataTaxonomyDown:
                    self.wikidataTaxonomyDown[obj] = set()
                self.wikidataTaxonomyDown[obj].add(subject)
    
    def result(self):
        return self.wikidataTaxonomyDown

###########################################################################
#           Creating the YAGO taxonomy
###########################################################################

# Classes that will not be added to YAGO, and whose children won't be added either
badClasses = {
    "wd:Q17379835",   # Wikimedia page outside the main knowledge tree
    "wd:Q4167836",    # Wikimedia category
    "wd:Q15138389",   # Wikimedia article page
    "wd:Q17362920",   # Wikimedia duplicate page
    "wd:Q21286738",   # Wikimedia suplucate item
    "wd:Q17442446",   # Wikimedia internal stuff
    "wd:Q15474042",   # same
    "wd:Q111279923",  # same 
    "wd:Q4167410",    # disambiguation page
    "wd:Q13406463",   # list article
    "wd:Q17524420",   # aspect of history
    "wd:Q18340514",   # article about events in a specific year or time period
    "wd:Q24017414",   # second-order class
    "wd:Q12335479",   # templates
    "wd:Q12139612",   # Lists
    "wd:Q80096233",   # Lists
    "wd:Q88392887",   # scholarly articles, tweets, etc.
    "wd:Q591041",     # same
    "wd:Q13442814",   # same
    "wd:Q3523102",    # same
    "wd:Q115668308",  # Release    
    "wd:Q618123",     # geographical feature
    "wd:Q13226383",   # facility
    "wd:Q2221906",    # geographical location
    "wd:Q15642541",   # human-geographic territorial entity    
    "wd:Q4835091",    # territory
    "wd:Q4026292",    # Action
    "wd:Q67518978",   # Occurrent
    "wd:Q2545446",    # Graphemes
    "wd:Q32483",      # Characters
    "wd:Q3241972",    # Characters
    "wd:Q29654788",   # Unicode characters
    "wd:Q11953984",   # Linguistic units, words etc
    "wd:Q11563",      # Numbers,
    "wd:Q107467117",  # Type of award
    "wd:Q19478619",   # Meta-class
    "wd:Q5127848",    # Class
    "wd:Q192581",     # Job -> causes problem because instances of "lawyer" become instances of "job" and thus of "economic activity"
    "wd:Q12737077",   # Occupation (dito)
    "wd:Q28640",      # Profession (dito)
    "wd:Q4164871"    # Role (dito)
}

def disjointClasses(class_, taxonomyUp, yagoSchema):
    """Yields the set of classes that are disjoint with class_"""
    if class_ in yagoSchema.classes:
        yield from yagoSchema.classes[class_].disjointWith
    for superClass in taxonomyUp.get(class_, []):
        yield from disjointClasses(superClass, taxonomyUp, yagoSchema)
    
def ancestors(class_, taxonomyUp):
    """ Yields the ancestors of class_ (including class_ itself)"""
    yield class_
    for superClass in taxonomyUp.get(class_, []):
        yield from ancestors(superClass, taxonomyUp)
    
def addSubClass(superClass, subClass, yagoSchema, yagoTaxonomyUp, wikidataTaxonomyDown, stats):
    """Adds the subClass (and all its subclasses in wikidataTaxonomyDown) to the superClass in yagoTaxonomyUp, excluding bad classes, loops, and disjoint classes"""
    
    # Exclude bad classes
    if subClass in badClasses:
        return
    
    # Convert ancestors generator to set for efficient membership checks
    superAncestors = set(ancestors(superClass, yagoTaxonomyUp))
    
    # Exclude loops
    if subClass in superAncestors:
        stats['loops'] += 1
        return
    
    # Exclude classes that are already mapped to YAGO
    if subClass in yagoSchema.wikidataClasses:
        return
    
    # Treat classes that appear already in the taxonomy
    if subClass in yagoTaxonomyUp:
        # Convert ancestors to set for efficient membership check
        subAncestors = set(ancestors(subClass, yagoTaxonomyUp))
        
        # The current path is shorter than the one that exists -> abandon this path
        if superClass in subAncestors:
            stats['shortcuts'] += 1
            return
        
        # The current path is longer than the one that exists -> abandon the other one
        # Make a list before iterating because we modify the taxonomy
        for existingSuperClass in list(yagoTaxonomyUp[subClass]):
            if existingSuperClass in superAncestors:
                stats['shortcuts'] += 1
                yagoTaxonomyUp[subClass].discard(existingSuperClass)
        
        # Otherwise we have true multiple inheritance
        # Use set intersection for efficient disjoint check
        subDisjointSet = set(disjointClasses(subClass, yagoTaxonomyUp, yagoSchema))
        superDisjointSet = set(disjointClasses(superClass, yagoTaxonomyUp, yagoSchema))
        if subDisjointSet & superDisjointSet:
            stats['disjoint'] += 1
            return
    
    yagoTaxonomyUp[subClass].add(superClass)
    # Sort the classes to have a deterministic algorithm
    for subSubClass in sorted(wikidataTaxonomyDown.get(subClass, [])):    
        addSubClass(subClass, subSubClass, yagoSchema, yagoTaxonomyUp, wikidataTaxonomyDown, stats)        
        
###########################################################################
#           Main
###########################################################################

def main():
    with TsvUtils.Timer("Step 02: Creating YAGO taxonomy"):
        # Load YAGO schema
        yagoSchema = Schema.YagoSchema(SCHEMA_FILE)
        
        # Create YAGO taxonomy as a dictionary
        yagoTaxonomyUp = defaultdict(set)
        for subClass in yagoSchema.classes.values():
            for superClass in subClass.superClasses:
                yagoTaxonomyUp[subClass.identifier].add(superClass.identifier)
            
        # Load Wikidata taxonomy
        results = TurtleUtils.visitWikidata(WIKIDATA_FILE, WikidataVisitor)
        
        # <results> is a list of taxonomies
        # We now merge them together in the global variable <wikidataTaxonomyDown>
        wikidataTaxonomyDown = {}
        for result in results:
            for key in result:
                if key not in wikidataTaxonomyDown:
                    wikidataTaxonomyDown[key] = set()
                wikidataTaxonomyDown[key].update(result[key])                
        print("  Info: Total number of Wikidata classes:", len(wikidataTaxonomyDown))
        print("  Info: Total number of Wikidata links:", sum(len(wikidataTaxonomyDown[class_]) for class_ in wikidataTaxonomyDown))        
        
        # Initialize statistics counter
        stats = {'loops': 0, 'shortcuts': 0, 'disjoint': 0}
        
        # Now we merge the Wikidata taxonomy into the YAGO taxonomy
        for yagoClass in yagoSchema.classes.values():
            for wikidataClass in yagoClass.fromClasses:            
                for wikidataSubclass in wikidataTaxonomyDown.get(wikidataClass, []):
                    addSubClass(yagoClass.identifier, wikidataSubclass, yagoSchema, yagoTaxonomyUp, wikidataTaxonomyDown, stats)

        print("  Info: Loops removed:", stats['loops'])
        print("  Info: Shortcuts removed:", stats['shortcuts'])
        print("  Info: Disjoint links removed:", stats['disjoint'])

        # Write resulting taxonomy
        print("  Writing taxonomy...", end="", flush=True)
        with TsvUtils.TsvFileWriter(OUTPUT_FOLDER+"02-yago-taxonomy-to-rename.tsv") as taxonomyWriter:
            for class_ in yagoTaxonomyUp:
                for superClass in yagoTaxonomyUp[class_]:
                    taxonomyWriter.writeFact(class_, "rdfs:subClassOf", superClass)
        print("done")

if __name__ == '__main__':
    main()
    if TEST:
        Evaluator.compare(OUTPUT_FOLDER+"02-yago-taxonomy-to-rename.tsv")