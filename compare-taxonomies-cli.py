import sys
from wasabi import msg, table

# cli version of compare-taxonomies.py
# to use program: 
# 1. start the environment (recommended) with pipenv shell
# 2. python3 compare-taxonomies.py [path to gold standard file] [path to output file]
if __name__ == '__main__':
    print()
    msg.info("Initiated...")
    gold_standard = "" # standard file path
    output_file = ""
    not_in_output = []
    not_in_gold = []
    num_output = 0
    num_gold = 0
    halt = False # to exit the program later after an error has been detected (and not get stack problems)
    
    try:
        # reads file paths from args
        gold_standard = sys.argv[1]
        output_file = sys.argv[2]
        msg.text(f"gold standard: {str(gold_standard)}")
        msg.text(f"output file: {str(output_file)}")
    except:
        msg.fail("Problem with arguments provided. Please provide the path to the gold standard file and the output file to test.")
        halt = True

    if halt:
        exit()

    with msg.loading("Analyzing the files..."):
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
        exit()

    print()
    msg.good("Files analyzed successfully!")
    print()
    msg.text(f"Number of files in golden standard and not in output file: {len(not_in_output)}")
    msg.text("Lines:", color="yellow")
    for line in not_in_output:
        msg.text(f"\t{str(line)}")
    print()
    msg.text(f"Number of files in output file and not in golden standard: {len(not_in_gold)}")
    msg.text("Lines:", color="yellow")
    for line in not_in_gold:
        msg.text(f"\t{str(line)}")
    print()

    # todo: check the statistics because I am not sure they are correct
    msg.text("Statistics:", color="yellow")
    precision = round((num_gold - len(not_in_output)) / num_gold, 3)
    recall = round((num_output - len(not_in_gold)) / num_output, 3)
    data = [(precision, recall)]
    header = ("Precision", "Recall")
    widths = (10, 10)
    aligns = ("l", "l")
    # formatted = table(data, header=header, divider=True, widths=widths, aligns=aligns)
    msg.table(data, header=header, divider=True, widths=widths, aligns=aligns)