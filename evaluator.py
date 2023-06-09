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
    gold_standard = f"{output_file[0:-4]}-gold.tsv" if gold_file == None else gold_file # standard file path

    with open(gold_standard, encoding='utf8') as gold:
        goldContent=set(gold)
        with open(output_file, encoding='utf8') as out:
            outContent = set(out)
            not_in_output = goldContent.difference(outContent)
            not_in_gold = outContent.difference(goldContent)

    print(f"  Lines in the gold standard that are not in the output file: {len(not_in_output)}")
    for line in not_in_output:
        try:
            print(f"    {str(line)}", end="")        
        except:
            # too idiotic to print
            pass
    print(f"  Lines in output file that are not in the gold standard: {len(not_in_gold)}")
    for line in not_in_gold:
        try:
            print(f"    {str(line)}", end="")
        except:
            # too idiotic to print
            pass
    if len(not_in_output)==0 and len(not_in_gold)==0:
        print("OK!")
    else:
        print("FAILED!")

# quick test
if __name__ == '__main__':
    compare("test-data/02-make-taxonomy/02-yago-taxonomy.tsv")