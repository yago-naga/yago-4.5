import sys
from wasabi import msg
import csv

if __name__ == '__main__':
    msg.info("Initiated...")
    gold_standard = ""
    output_file = ""
    not_in_output = []
    not_in_gold = []
    halt = False
    
    try:
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
        try:
            with open(gold_standard) as file:
                with open(output_file) as file2:
                    not_in_output = set(file).difference(file2)
            
            file.close()
            file2.close()

            with open(output_file) as file:
                with open(gold_standard) as file2:
                    not_in_gold = set(file).difference(file2)

            file.close()
            file2.close()                          
           
        except FileNotFoundError:
            msg.fail(f"Invalid file path for {err_file} file.")
            halt = True

    if halt:
        exit()

    msg.good("Files analyzed successfully!")
    msg.text(f"Number of files in golden standard and not in output file: {len(not_in_output)}")
    msg.text("Lines:", color="yellow")
    for line in not_in_output:
        msg.text(f"\t{str(line)}")
    msg.text(f"Number of files in output file and not in golden standard: {len(not_in_gold)}")
    msg.text("Lines:", color="yellow")
    for line in not_in_gold:
        msg.text(f"\t{str(line)}")
