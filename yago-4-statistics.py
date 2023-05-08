"""
Produces statistics about YAGO 4 entities and predicates
   
"""

import sys
import glob
import re
import evaluator
import itertools
import TurtleUtils
import TsvUtils
import random
import os
import Prefixes
from collections import defaultdict

###########################################################################
#           Removing shortcuts
###########################################################################

yagoTaxonomyUp=defaultdict(set)

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
 
##########################################################################
#             Main
##########################################################################

with TsvUtils.Timer("Collecting YAGO 4 statistics"):

    for triple in TsvUtils.tsvTuples("../yago-4/classes.nt", "  Loading YAGO taxonomy"):
        if len(triple)>3:
            yagoTaxonomyUp[triple[0]].add(triple[2])
            
    print("  Taxonomic links before shortcut removal:", sum(len(yagoTaxonomyUp[s]) for s in yagoTaxonomyUp))
    removeShortcuts():
    print("  Taxonomic links after shortcut removal:", sum(len(yagoTaxonomyUp[s]) for s in yagoTaxonomyUp))