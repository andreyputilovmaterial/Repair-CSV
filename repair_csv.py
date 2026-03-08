import re, time
# from collections import Counter
from collections import defaultdict
# from itertools import product
from itertools import combinations
from collections import deque
import argparse
import traceback, sys # for error reporting - to print to stderr
from pathlib import Path
from datetime import datetime
# import random
import codecs
import io
import csv



# =======================
# CONFIGURATION
# =======================
DELIMITER = ","
CHECK_COLUMNS = 10
THRESHOLD = 0.76
# LIMIT_MAX_NUM_OF_SIGNATURES = 11000
DEFAULT_OPTIONS = {
    # ...
}
DEFAULT_CSV_LOAD_PROVIDER = 'csv_module'
# =======================






get_not_implemented_cb = lambda feature_name: lambda *args, **kwargs: (_ for _ in ()).throw(NotImplementedError('"{f}" not implemented.'.format(f=feature_name)))

def parse_csv_line_text_basic(line,delimiter,max_columns,config):
    parts = line.rstrip("\r\n").split(delimiter)
    if max_columns is not None:
        parts = parts[:max_columns]
    while len(parts) < max_columns:
        parts.append("#N/A")
    return parts

def parse_csv_line_text_advanced(line,delimiter,max_columns,config):
    parts = []
    line.rstrip("\r\n")
    field = ''
    in_quotes = False
    n = len(line)
    i = 0
    while i<n:
        c = line[i]

        if c == '"':
            if in_quotes and i+1 < n and line[i+1] == '"':
                field += '"'
                i += 1
            else:
                in_quotes = not in_quotes
        
        elif c == delimiter and not in_quotes:
            if max_columns is not None and len(parts)+1>=max_columns:
                break
            parts.append(field)
            field = ''
        
        else:
            field += c
        
        i += 1
    
    parts.append(field)

    if max_columns is not None:
        parts = parts[:max_columns]
    while len(parts) < max_columns:
        parts.append("#N/A")
    return parts

def parse_csv_line_csvmodule(line,delimiter,max_columns,config):
    line.rstrip("\r\n")
    parts = next(csv.reader([line],delimiter=delimiter))
    if max_columns is not None:
        parts = parts[:max_columns]
    while len(parts) < max_columns:
        parts.append("#N/A")
    return parts

csv_readers = {
    'basic': parse_csv_line_text_basic,
    'text_advanced': parse_csv_line_text_advanced,
    'csv_module': parse_csv_line_csvmodule,
}







def parse_csv_line(line,config):
    reader = config['csv_reader']
    if not callable(reader):
        # I know not a pythonic way to validate everything, but I prefer to see descriptive errors early
        # sorry, this is just much easier for me
        # I don't have to follow dogmas
        # anyway, "defensive programming" is also a possiblee approach
        raise TypeError('Error: CSV Reader: not callable') 
    delimiter = config['delimiter']
    max_columns = config['check_columns']
    return reader(line,delimiter,max_columns,config)

def classify_cell(cell):
    cell = cell.strip()
    if re.match(r'^\s*#N/A$',cell):
        return "(sysmissing)"
    elif re.match(r'^\s*$',cell):
        return "(empty)"
    elif re.match(r'^\s*1\s*$', cell):
        return "(binary-always-1)"
    elif re.match(r'^\s*0\s*$', cell):
        return "(binary-always-0)"
    elif re.match(r'^\s*[01]\s*$', cell):
        return "(binary)"
    elif re.match(r'^\s*\d+\s*$', cell):
        return "(number-integer)"
    elif re.match(r'^\s*[\+-]*\s*\d*\.\d+\s*$', cell):
        return "(number-real)"
    else:
        return "(text-any)"

def get_signature(line,config):
    parts = parse_csv_line(line,config)
    return tuple(classify_cell(c) for c in parts)

def get_signature_weight(sig):
    weights = {
        '(sysmissing)': 1,
        '(empty)': 0.25,
        '(binary-always-1)': 0.49,
        '(binary-always-0)': 0.49,
        '(binary)': 0.47,
        '(number-integer)': 0.33,
        '(number-real)': 0.32,
        '(text-any)': 0.00001,
    }
    def wgt(el):
        if el in weights:
            return weights[el]
        else:
            raise Exception('Trying to find weight for signature: unknown element: {el}'.format(el=el))
    return sum(map(wgt,sig))

# def derive_signatures(sig_original):
#     possible_transformations = {
#         '(empty)': ['(binary)','(number-integer)','(number-real)','(text-any)'],
#         # '(binary)': ['(number-integer)','(number-real)','(text-any)'],
#         '(binary)': ['(number-integer)','(number-real)','(text-any)'],
#         '(number-integer)': ['(number-real)','(text-any)'],
#         '(number-real)': ['(text-any)'],
#     }
#     for transform_flags in product([False,True], repeat=len(sig_original)):
#         transformations_matrix = (
#             (possible_transformations[original_value] if original_value in possible_transformations else []) if transformation_flag else [original_value]
#             for transformation_flag, original_value in zip(transform_flags,sig_original)
#         )
#         combinations = list(product(*transformations_matrix))
#         yield from combinations
class CommonSignatureNotFound(Exception):
    """Raised when common of 2 signatures is not found, and should be caught"""
    pass
def find_common_signature_denominator(sig1, sig2):

    possible_transformations = {
        '(sysmissing)': [],
        '(empty)': ['(binary-always-1)','(binary-always-0)','(binary)','(number-integer)','(number-real)','(text-any)'],

        '(binary-always-0)': ['(binary)'],
        '(binary-always-1)': ['(binary)'],

        '(binary)': ['(number-integer)'],
        '(number-integer)': ['(number-real)'],
        '(number-real)': ['(text-any)'],
    }
    def reachable_with_distance(start):
        distances = {start: 0}
        queue = deque([start])

        while queue:
            node = queue.popleft()
            for nxt in possible_transformations.get(node, []):
                if nxt not in distances:
                    distances[nxt] = distances[node] + 1
                    queue.append(nxt)

        return distances


    def closest_common(a, b):
        da = reachable_with_distance(a)
        db = reachable_with_distance(b)

        common = set(da) & set(db)

        if not common:
            raise CommonSignatureNotFound('Common of {a} and {b} not found. Can\'t find derived signature that is common for both input signatiures'.format(a=a,b=b))

        return min(common, key=lambda x: da[x] + db[x])

    return tuple(closest_common(spec1,spec2) for spec1,spec2 in zip(sig1,sig2))

def is_signature_matching(sig1, sig2):

    possible_transformations = {
        '(sysmissing)': [],
        '(empty)': ['(binary-always-1)','(binary-always-0)','(binary)','(number-integer)','(number-real)','(text-any)'],

        '(binary-always-0)': ['(binary)'],
        '(binary-always-1)': ['(binary)'],

        '(binary)': ['(number-integer)'],
        '(number-integer)': ['(number-real)'],
        '(number-real)': ['(text-any)'],
    }
    def reachable_with_distance(start):
        distances = {start: 0}
        queue = deque([start])

        while queue:
            node = queue.popleft()
            for nxt in possible_transformations.get(node, []):
                if nxt not in distances:
                    distances[nxt] = distances[node] + 1
                    queue.append(nxt)

        return distances


    def closest_common(a, b):
        da = reachable_with_distance(a)
        db = {b:0}

        common = set(da) & set(db)

        if not common:
            raise CommonSignatureNotFound('Common of {a} and {b} not found. Can\'t find derived signature that is common for both input signatiures'.format(a=a,b=b))

        return min(common, key=lambda x: da[x] + db[x])

    result = tuple(closest_common(spec1,spec2) for spec1,spec2 in zip(sig1,sig2))
    return not not result




class PerformanceMonitor:
    def __init__(self,config={}):
        self.__config = config
        self.progress = None
        self.time_started = None
        self.time_last_reported = None
        self.progress_last_reported = None
        self.userprovideddata_totalrecords = config['total_records'] if 'total_records' in config else None
        self.config_frequency_records = config['report_frequency_records_count'] if 'report_frequency_records_count' in config else None
        self.config_frequency_timeinterval = config['report_frequency_timeinterval'] if 'report_frequency_timeinterval' in config else None
        self.config_text_pipein = config['report_text_pipein'] if 'report_text_pipein' in config and config['report_text_pipein'] else 'progress'
    
    def __iter__(self):
        self.progress = 0
        self.time_started = time.time()
        self.time_last_reported = self.time_started
        self.progress_last_reported = -1
        return self
    
    def _calc_eta(self,time_now=None):
        def calc_eta(time_start,time_now,records_expected_total,records_now):
            return (1*time_start+int((time_now-time_start)*(records_expected_total/records_now)))
        if self.userprovideddata_totalrecords is None:
            return None
        if not time_now:
            time_now = time.time()
        time_started = self.time_started
        return calc_eta(time_started,time_now,self.userprovideddata_totalrecords,self.progress)

    def __next__(self):
        def fmt_duration(seconds):
            def fmt(v):
                v = '{v}'.format(v=v)
                return re.sub(r'(\.[1-9]\d*?)[0]{3}\d*',lambda m: m[1],v,flags=re.I|re.DOTALL)
            if seconds<300:
                return '{n} seconds'.format(n=fmt(int(seconds)))
            else:
                if seconds<6000:
                    return '{n} minutes'.format(n=fmt(0.1*int(seconds/6)))
                else:
                    return '{n} hours'.format(n=fmt(0.1*int(seconds/360)))
        self.progress = self.progress + 1
        if (self.config_frequency_records is None) or (self.progress - self.progress_last_reported > self.config_frequency_records):
            time_now = time.time()
            if (self.config_frequency_timeinterval is None) or ((time_now - self.time_last_reported)>self.config_frequency_timeinterval):
                eta = self._calc_eta(time_now)
                print( '{text_pipe}: processing {nline}{display_out_total}{display_details}'.format(
                    nline = self.progress,
                    display_out_total = ' / {nlinetotal}'.format(nlinetotal=self.userprovideddata_totalrecords) if (self.userprovideddata_totalrecords is not None) else '',
                    display_details = ' ({per}%{details_eta})'.format(
                        per = round(self.progress*100/self.userprovideddata_totalrecords,1),
                        details_eta = ', remaining: {remaining}, ETA: {eta}'.format(
                            remaining = fmt_duration(eta-time_now),
                            eta = '{t}'.format(t=time.strftime('%m/%d/%Y %H:%M:%S',time.localtime(eta))),
                        ) if eta else '',
                    ) if (self.userprovideddata_totalrecords is not None) else '',
                    text_pipe = self.config_text_pipein,
                ))
                self.progress_last_reported = self.progress
                self.time_last_reported = time_now
        return None
















def pre_read(input_file,config):
    # -----------------------
    # PHASE 1 - detect pattern
    # -----------------------
    print('')
    print('Phase 1, pre-reading csv to compile the list of signatures...')
    print('INPUT: {f}'.format(f=input_file))
    print('')

    config_updated = {}
    total_rows = 0
    signature_counter = defaultdict(set)
    performance_counter = iter(PerformanceMonitor(config={
        'total_records': None, # float('inf'),
        'report_frequency_records_count': 10,
        'report_frequency_timeinterval': 11
    }))
    with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
        next(f)  # skip header
        for line_number, line in enumerate(f):
            next(performance_counter)
            sig_strict = get_signature(line,config)
            signature_counter[sig_strict].add(line_number)
            total_rows += 1
    
    # derived combinations
    print('done reading, compiling the final list of signatures...')
    signature_counter_with_derived = signature_counter.copy() # shallow copy, existing values, that are sets, are shared
    for sig1, sig2 in combinations(signature_counter.keys(), 2):
        try:
            sig_common_denominator = find_common_signature_denominator(sig1, sig2)
            if sig_common_denominator not in signature_counter_with_derived:
                signature_counter_with_derived[sig_common_denominator] = set()
            # we found a common - add
            signature_counter_with_derived[sig_common_denominator].update(
                signature_counter[sig1],
                signature_counter[sig2],
            ) # should be a set of rows
        except CommonSignatureNotFound:
            # do not add - no derived of those two
            pass

    config_updated['row_count'] = total_rows
    config_updated['signatures_strict'] = signature_counter.keys()
    config_updated['signatures_with_derived_final'] = signature_counter_with_derived
    # print('for debugging: signature strict count: {l}'.format(l=len(config_updated['signatures_strict'])))
    # print('for debugging: signature with derived final count: {l}'.format(l=len(config_updated['signatures_with_derived_final'])))

    # and final cb to check if signature of current line matches
    def check_cb(line,signature):
        sig_strict = get_signature(line,config)
        try:
            return is_signature_matching(sig_strict, signature)
        except CommonSignatureNotFound:
            return False
    config_updated['is_signature_match'] = check_cb

    return config_updated




def find_most_common_sig(signature_counter,config):
    # most_common_sig, count = signature_counter.most_common(1)[0]
    most_common_sig = max(
        signature_counter,
        key = lambda sig: len(signature_counter[sig]) * get_signature_weight(sig)
    )
    count = len(signature_counter[most_common_sig])
    ratio = count / config['row_count']
    threshold = float(config['threshold']) / 100

    print('statistics: total number of signatures to check: {l}'.format(l=len(signature_counter)))
    print('')
    print("Most common signature:", most_common_sig)
    # print('{c} lines matching ({n}% - threshold is {t}%)'.format(c=count,n=round(ratio*10000)/100,t=round(threshold*10000)/100))
    print('{c} lines matching ({n}%)'.format(c=count,n=round(ratio*10000)/100))
    print('')

    if ratio < threshold:
        raise Exception("No dominant signature found")
    
    return most_common_sig
    




def write_updated_file(input_file,output_file,check_match,config):
    # -----------------------
    # PHASE 2 - repair file
    # -----------------------
    print('')
    print('Phase 2, writing out the repaired file...')
    print('OUTPUT: {f}'.format(f=output_file))
    print('')

    statistics_lines_processed = 0
    statistics_lines_correct = 0
    statistics_lines_merged = 0
    statistics_lines_written = 0

    is_debug = 'debug_flags' in config and 'line_num_investigation' in config['debug_flags'] and config['debug_flags']['line_num_investigation']

    bom = None
    bom_len = 0
    with open(input_file,'rb') as f:
        starting_bytes = f.read(4)
        for candidate in (
            codecs.BOM_UTF8,
            codecs.BOM_UTF16_LE,
            codecs.BOM_UTF16_BE,
            codecs.BOM_UTF32_LE,
            codecs.BOM_UTF32_BE,
        ):
            if starting_bytes.startswith(candidate):
                bom = candidate
                bom_len = len(bom)
                break
    
    with open(input_file, 'rb') as f_in, \
        open(output_file, 'wb') as f_out:

        if bom:
            f_out.write(bom)
        f_in.seek(bom_len)

        f = io.TextIOWrapper(f_in, encoding='utf-8')
        out = io.TextIOWrapper(f_out, encoding='utf-8')

        # header
        line = next(f)
        line = line.rstrip('\r\n')
        if is_debug:
            line = 'DEBUG'+config['delimiter']+line
        out.write(line + '\n')

        current_line = None
        current_line_line_number_first = None
        current_line_line_number_last = None
        lines_matching_signature = config['signatures_with_derived_final'][config['most_common_sig']]
        performance_counter = iter(PerformanceMonitor(config={
            'total_records': config['row_count'],
            'report_frequency_records_count': 10,
            'report_frequency_timeinterval': 11
        }))
        for line_number, line in enumerate(f):
            try:
                next(performance_counter)
                statistics_lines_processed += 1
                line = line.rstrip('\r\n')
                is_good = check_match(line)
                is_good_alternative_verify = line_number in lines_matching_signature
                assert is_good == is_good_alternative_verify, 'Khm, checking if line matches signature, something is off'
                if is_good:
                    statistics_lines_correct += 1
                    if current_line:
                        if is_debug:
                            current_line = 'line #{n} (source line #{l1}:{l2})'.format(n=statistics_lines_written+1,l1=current_line_line_number_first+1,l2=current_line_line_number_last+1)+config['delimiter'] + current_line
                        out.write(current_line + '\n')
                        statistics_lines_written += 1
                    current_line = line
                    current_line_line_number_first = line_number
                    current_line_line_number_last = line_number
                else:
                    statistics_lines_merged += 1
                    if current_line is None:
                        raise Exception('Even first line does not match the signature pattern. We can\'t merge it with previous because there\'s no previous. Please review carefully. Stop.')
                    current_line = re.sub(r'\s*$','',current_line) + ' ' + re.sub(r'^\s*','',line)
                    current_line_line_number_last = line_number
            except Exception as e:
                print('Failed when processing line #{l}'.format(l=line_number,file=sys.stderr))
                try:
                    print('Line starting: "{l}..."'.format(l=line[:32],file=sys.stderr))
                except:
                    pass
                try:
                    print('Signature: {l}'.format(l=get_signature(line,config),file=sys.stderr))
                except:
                    pass
                raise e
        if current_line:
            if is_debug:
                current_line = 'line #{n} (source line #{l1}:{l2})'.format(n=statistics_lines_written+1,l1=current_line_line_number_first+1,l2=current_line_line_number_last+1)+config['delimiter'] + current_line
            out.write(current_line + '\n')
            statistics_lines_written += 1
    
    print('statistics: lines processed: {l}'.format(l=statistics_lines_processed))
    print('statistics: lines correct: {l}'.format(l=statistics_lines_correct))
    print('statistics: lines merged: {l}'.format(l=statistics_lines_merged))
    print('statistics: lines written: {l}'.format(l=statistics_lines_written))
    assert statistics_lines_correct+statistics_lines_merged == statistics_lines_processed, 'Mismatch: lines processed != lines_correct + lines_merged'
    assert statistics_lines_correct == statistics_lines_written, 'Mismatch: lines correct != lines_written'
    print('writing to file has finished')





def main():
    try:
        time_start = datetime.now()
        parser = argparse.ArgumentParser(
            description="FIX-CSV-Utility",
            prog='fix_csv'
        )
        parser.add_argument(
            '-1',
            '--input',
            help='Input CSV file to read and inspect',
            metavar='CSV_FILE',
            type=str,
            required=True,
        )
        parser.add_argument(
            '--output',
            help='Final repaired CSV file to write to',
            metavar='REPAIRED_CSV_FILE',
            type=str,
            required=False
        )
        parser.add_argument(
            '--delimiter',
            help='CSV separator (Usually \',\' \';\' or \'TAB\'. default is \',\' comma.)',
            type=str,
            metavar='CHAR',
            required=False
        )
        parser.add_argument(
            '--debug-mode-features',
            help='Special functions for debugging (comma-separated list of features to enable)',
            type=str,
            metavar='FLAG1,FLAG2,FLAG3',
            required=False
        )
        parser.add_argument(
            '--config-options',
            help='Special flags to control behavior (comma-separated list of flags)',
            type=str,
            metavar='FLAG1,FLAG2,FLAG3',
            required=False
        )
        parser.add_argument(
            '--csv-reader',
            help='CSV parsing mode',
            type=str,
            # choices=csv_readers.keys(),
            choices=[t for t in csv_readers.keys()]+['test'], # TODO: DEBUG
            default=DEFAULT_CSV_LOAD_PROVIDER
        )
        parser.add_argument(
            '--check-columns',
            help='Number of columns to check at the beginning of each line (default is 10)',
            type=int,
            required=False
        )
        parser.add_argument(
            '--threshold',
            help='Threshold, for how many lines should follow the pattern (expressed in percentages)',
            type=float,
            required=False
        )
        # args, args_rest = parser.parse_known_args()
        args = parser.parse_args()

        config = {}

        input_file = None
        if args.input:
            input_file = Path(args.input)
            input_file = '{input_file}'.format(input_file=input_file.resolve())
        else:
            raise FileNotFoundError('Inp source: file not provided; please use --csv_file')
        if not(Path(input_file).is_file()):
            raise FileNotFoundError('file not found: {fname}'.format(fname=input_file))
        input_file = '{f}'.format(f=input_file) # convert back to string

        config['debug_flags'] = {}
        if args.debug_mode_features:
            known_debug_flags = [
                'line_num_investigation'
            ]
            flags = list(f.strip() for f in args.debug_mode_features.split(',') if f.strip())
            for f in flags:
                if f in known_debug_flags:
                    config['debug_flags'][f] = True
                    print('DEBUG FEATURE ON: {f}'.format(f=f))
                else:
                    raise Exception('debug flag is not in known debug flags')

        config['options'] = {**DEFAULT_OPTIONS}
        if args.config_options:
            known_debug_flags = [
            ]
            flags = list(f.strip() for f in args.config_options.split(',') if f.strip())
            for f in flags:
                if f in known_debug_flags:
                    config['options'][f] = True
                    print('CONFIG OPTION ON: {f}'.format(f=f))
                else:
                    raise Exception('debug flag is not in known debug flags')

        output_file = None
        if args.output:
            output_file = Path(args.output)
            output_file = '{output_file}'.format(output_file=output_file.resolve())
        else:
            output_file = Path(input_file).with_name(Path(input_file).stem + '.repaired' + Path(input_file).suffix)
        if Path(input_file).resolve() == Path(output_file).resolve():
            raise Exception('Output file has to be a different file!')
        output_file = '{f}'.format(f=output_file) # convert back to string

        config['csv_reader'] = get_not_implemented_cb('csv_reader_not_specified')
        if args.csv_reader:
            reader = args.csv_reader.strip()
            if reader in csv_readers:
                config['csv_reader'] = csv_readers[reader]
            else:
                # raise Exception('CSV reader not provided: {s}'.format(s=args.csv_reader)) # still better than KeyError; however, argparse should handle it anyway
                config['csv_reader'] = get_not_implemented_cb('CSV Reader: '+reader)
        else:
            # raise Exception('CSV reader not provided: {s}'.format(s=args.csv_reader))
            config['csv_reader'] = get_not_implemented_cb('CSV Reader: '+reader)

        if args.threshold:
            try:
                config['threshold'] = float(args.threshold)
            except Exception as e:
                raise Exception('Failed to parse the "threshold" param: "{value}"'.format(value=args.threshold)) from e
        else:
            config['threshold'] = THRESHOLD

        if args.delimiter:
            try:
                config['delimiter'] = args.delimiter
                if re.match(r'^\s*tab\s*$',config['delimiter'],flags=re.I):
                    config['delimiter'] = '\t'
            except Exception as e:
                raise Exception('Failed to parse the "delimiter" param: "{value}"'.format(value=args.delimiter)) from e
        else:
            config['delimiter'] = DELIMITER

        if args.check_columns:
            try:
                config['check_columns'] = int(args.check_columns)
            except Exception as e:
                raise Exception('Failed to parse the "check_columns" param: "{value}"'.format(value=args.check_columns)) from e
        else:
            config['check_columns'] = CHECK_COLUMNS

        print('{script}: script started at {dt}'.format(dt=time_start,script=parser.prog))

        config = {**config,**pre_read(input_file,config)}
        config['input_filename'] = input_file
        config['output_filename'] = output_file
        config['time_start'] = time_start

        # check_cb = detect_pattern(input_file,config)
        most_common_sig = find_most_common_sig(config['signatures_with_derived_final'],config)
        config['most_common_sig'] = most_common_sig
        cb = config['is_signature_match']
        def check_cb(line):
            return cb(line,most_common_sig)

        write_updated_file(input_file,output_file,check_cb,config)

        time_finish = datetime.now()
        print('{script}: finished at {dt} (elapsed {duration})'.format(script=parser.prog,dt=time_finish,duration=time_finish-time_start))
        
    except Exception as e:
        # the program is designed to be user-friendly
        # that's why we reformat error messages a little bit
        # stack trace is still printed (I even made it longer to 20 steps!)
        # but the error message itself is separated and printed as the last message again

        # for example, I don't write "print('File Not Found!');exit(1);", I just write "raise FileNotFoundErro()"
        print('',file=sys.stderr)
        print('Stack trace:',file=sys.stderr)
        print('',file=sys.stderr)
        traceback.print_exception(e,limit=20)
        print('',file=sys.stderr)
        print('',file=sys.stderr)
        print('',file=sys.stderr)
        print('Error:',file=sys.stderr)
        print('',file=sys.stderr)
        print('{e}'.format(e=e),file=sys.stderr)
        print('',file=sys.stderr)
        exit(1)



if __name__ == '__main__':
    main()
