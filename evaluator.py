"""
Compares two text files line by line

(c) 2022  Paola Ortega Saborio and Fabian M. Suchanek
   
"""

def compare(output_file, gold_file=None):
    """ Compares 2 text files line by line and prints precision and recall
        Parameters: the file to be tested and (optionally) the gold file 
                    if the gold file is not given, defaults to XXX-gold.tsv
        Returns: 0 if comparison is successful, 
                 -1 if there were problems reading the files"""
    print("Evaluating "+output_file)
    gold_standard = f"{output_file[0:-4]}-gold.tsv" if gold_file == None else f"{gold_file}" # standard file path

    with open(gold_standard) as gold:
        goldContent=set(gold)
        with open(output_file) as out:
            outContent = set(out)
            not_in_gold = goldContent.difference(outContent)
            not_in_output = outContent.difference(goldContent)

    print(f"  Lines in the gold standard that are not in the output file: {len(not_in_output)}")
    for line in not_in_output:
        print(f"    {str(line)}", end="")
    print(f"  Lines in output file that are not in the gold standard: {len(not_in_gold)}")
    for line in not_in_gold:
        print(f"    {str(line)}", end="")

    precision = round((len(goldContent) - len(not_in_output)) / len(goldContent), 3)
    recall = round((len(outContent) - len(not_in_gold)) / len(outContent), 3)
    print("  Precision: ", precision)
    print("  Recall: ", recall)

# quick test
if __name__ == '__main__':
    compare("test-data/01-make-taxonomy/01-yago-taxonomy.tsv")