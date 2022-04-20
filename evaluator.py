"""
Compares two text files line by line

(c) 2022  Paola Ortega Saborio
   
"""

from wasabi import msg, table

def compare(output_file, gold_file=None):
    """ Compares 2 text files line by line and prints precision and recall
        Parameters: the file to be tested and (optionally) the gold file 
                    if the gold file is not given, defaults to XXX-gold.tsv
        Returns: 0 if comparison is successful, 
                 -1 if there were problems reading the files"""
    print()
    msg.info("Evaluating "+output_file)
    gold_standard = f"{output_file[0:-4]}-gold.tsv" if gold_file == None else f"{gold_file}" # standard file path
    output_file = f"{output_file}"
    not_in_output = []
    not_in_gold = []
    num_output = 0
    num_gold = 0
    halt = False # to exit the program later after an error has been detected (and not get stack problems)

    with msg.loading("  Analyzing the files..."):
        err_file = "gold standard"
        # instead of doing a double four loop, we use python's built-in set methods, which turn out to be faster and more efficient
        # todo: test with large data and ask Fabian if looking line by line instead of tab by tab works for him
        try:
            with open(gold_standard) as file:
                err_file = "output"
                with open(output_file) as file2:
                    not_in_output = set(file).difference(file2)
            
            file.close()
            file2.close()

            with open(output_file) as file:
                with open(gold_standard) as file2:
                    not_in_gold = set(file).difference(file2)

            file.close()
            file2.close()

            # obtaining total amount of lines for statistics
            with open(output_file) as file:
                num_output = len(file.readlines())

            with open(gold_standard) as file:
                num_gold = len(file.readlines())

            file.close()
            file2.close()                
           
        except FileNotFoundError:
            msg.fail(f"Invalid file path for {err_file} file.")
            halt = True

    if halt:
        return -1

    print()
    msg.text(f"  Number of files in golden standard and not in output file: {len(not_in_output)}")
    msg.text("  Lines:", color="yellow")
    for line in not_in_output:
        msg.text(f"\t{str(line)}")
    print()
    msg.text(f"  Number of files in output file and not in golden standard: {len(not_in_gold)}")
    msg.text("  Lines:", color="yellow")
    for line in not_in_gold:
        msg.text(f"\t{str(line)}")
    print()

    precision = round((num_gold - len(not_in_output)) / num_gold, 3)
    recall = round((num_output - len(not_in_gold)) / num_output, 3)
    data = [(precision, recall)]
    header = ("Precision", "Recall")
    widths = (10, 10)
    aligns = ("l", "l")
    msg.table(data, header=header, divider=True, widths=widths, aligns=aligns)
    return 1

# quick test
# if __name__ == '__main__':
#     compare("yago-taxonomy.tsv")