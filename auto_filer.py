
import logging
import os.path
import getpass
from os import scandir, rename
from sys import exit, exc_info
from yaml import safe_load

class InsufficientEntriesError(Exception):
    pass
class InvalidFileNameError(Exception):
    pass
class InvalidMatchError(Exception):
    pass

class File(object):
    def __init__(self, directory: str, file_name: str):
        self.name = file_name
        self.directory = directory
        self.path = os.path.join(directory, file_name)
        self.message = None
        self.data = {}
        self.target_par_dir = None
        self.target_sub_dir = None
        self.target_path = None

    def set_message(self, message: str):
        self.message = message

    def name_check(self, fields_config: dict) -> None:
        fn_fields = os.path.splitext(self.name)[0].split("-")
        if len(fn_fields) < len(fields_config):
            raise InsufficientEntriesError

        for i, field_val in enumerate(fields_config):
            field_name, req = list(field_val.items())[0]
            fn_field_str = fn_fields[i].strip()

            # raises error if invalid field name
            if req and fn_field_str.strip().upper() not in req:
                raise InvalidFileNameError(
                    f"Wrong name/value: \"{fn_field_str}\" for field: " +
                    f"{field_name.upper()} in position {i + 1}. " +
                    f"Should be one of the following: {req}")
            self.data[field_name] = fn_field_str

    # finds parent dir. skips file with error if there are multiple
    # matching folders or none found
    def find_par_dir(self, par_dir_field: str, target_paths: dict):

        # finds matching parent file
        parent_dirs = []
        for path_n, full_pn in target_paths.items():
            if self.data[par_dir_field].replace(" ", "").lower() in path_n:
                parent_dirs.append(full_pn)

        # raises error if there are multiple matching directory names
        if len(parent_dirs) > 1:
            raise InvalidMatchError(
                f"Found multiple matching {par_dir_field} folders: " +
                f"{list(map(os.path.basename, parent_dirs))}. " +
                "File name may need more detail")

        # raises error if does not match directories
        if not parent_dirs:
            raise InvalidMatchError(
                f"Could not find folder for " +
                f"{par_dir_field}: \"{self.data[par_dir_field]}\"")

        self.target_par_dir = parent_dirs[0]

    # finds sub directory. skips file with error if there are multiple
    # matching subdir, none found, or if file with same name exists.
    def find_sub_dir(self, sub_dir_field: str, par_dir_field: str):

        # finds matching sub directory
        sub_dirs = []
        for f in scandir(self.target_par_dir):
            if self.data[sub_dir_field].lower() in f.name.lower():
                sub_dirs.append(f.path)

        # raises error if missing subfolder
        if not sub_dirs:
            raise InvalidMatchError(
                f"{self.data[sub_dir_field]} folder not" +
                f" found in {par_dir_field} folder: " +
                f"..\\{os.path.basename(self.target_par_dir)}")

        # skips file if there are multiple matching subfolders
        if len(sub_dirs) > 1:
            raise InvalidMatchError(
                "Found multiple matching sub folders " +
                f"for: {self.data[sub_dir_field]} in " +
                f"..\\{os.path.basename(self.target_par_dir)}")

        # checks if target file already exists in project directory
        if os.path.isfile(os.path.join(sub_dirs[0], self.name)):
            raise InvalidMatchError(
                "Same filename already exists in " +
                f"..\\{os.path.basename(self.target_par_dir)}\\" +
                f"{os.path.basename(sub_dirs[0])}")

        self.target_sub_dir = sub_dirs[0]
        self.target_path = os.path.join(self.target_sub_dir, self.name)


class AutoFile(object):

    def __init__(self):
        self._skipped = 0
        self._total_files = 0
        self._matched_files = []
        self._failed_files = []


    def parse_config(self, config_f: str):
        try:
            f = open(config_f, "r")
            config = safe_load(f)

            self._fields_config = config["fields_config"]
            assert(isinstance(self._fields_config, (list)))

            self._source_path = config["source"]["path"]
            self._target_path = config["target"]["path"]
            assert(isinstance(self._source_path, (str)))
            assert(isinstance(self._target_path, (str)))

            self._source_recur = config["source"]["recursive"]
            self._target_recur = config["target"]["recursive"]
            assert(isinstance(self._source_recur, (bool)))
            assert(isinstance(self._target_recur, (bool)))

            self._source_ignore = config["source"]["ignore"]
            self._target_ignore = config["target"]["ignore"]
            assert(isinstance(self._source_ignore, (list)))
            assert(isinstance(self._target_ignore, (list)))

            self._par_dir_field = config["target"]["parent_dir"]
            self._sub_dir_field = config["target"]["sub_dir"]
            assert(isinstance(self._par_dir_field, (str)))
            assert(isinstance(self._sub_dir_field, (str)))

            f.close()

        except FileNotFoundError:
            print(f"Configuration file: \"{config_f}\" cannot be found. " +
                "Stopping operation")
            input("\npress ENTER to dismiss...\n")
            logging.exception("Failed to find configuration file")
            exit()

        except AssertionError:
            print("Configuration file format is invalid. Stopping operation")
            input("\npress ENTER to dismiss...\n")
            logging.exception("Corrupt configuration file format")
            exit()


        self._valid_source_target(self._target_path, self._source_path)

    def _valid_source_target(self, target: str, source: str):
        if not os.path.isdir(target):
            print(f"Target path is invalid:")
            input("\npress ENTER to dismiss...\n")
            exit()

        if not os.path.isdir(source):
            print(f"Source path is invalid:")
            input("\npress ENTER to dismiss...\n")
            exit()


    def run_matches(self):

        print("\nStarting Transfer...\n")
        target_paths = {}
        for f in scandir(self._target_path):
            if f.is_dir():
                target_paths[f.name.replace(" ", "").lower()] = f.path

        for root, _, filenames in os.walk(self._source_path):

            # skips directory if directory name in ignore list
            if any((path in root for path in self._source_ignore)):
                continue
            for fn in filenames:
                self._total_files += 1
                try:
                    s_file = File(root, fn)
                    s_file.name_check(self._fields_config)
                    s_file.find_par_dir(self._par_dir_field, target_paths)
                    s_file.find_sub_dir(self._sub_dir_field, self._par_dir_field)

                    common_path = os.path.commonpath(
                        [s_file.path, s_file.target_path])
                    common_bn = os.path.basename(common_path)

                    source_dir_shrt = os.path.join("..", common_bn, \
                        os.path.relpath(s_file.directory, common_path))
                    target_dir_shrt = os.path.join("..", common_bn, \
                        os.path.relpath(s_file.target_path, common_path))

                    s_file.set_message(
                        f"{'[[ MATCHED ]]':15}\"{s_file.name}\"\n" +
                        f"{'   From:':15}{source_dir_shrt}\n" +
                        f"{'   To:':15}{target_dir_shrt}\n")

                    # adds to matched if nothing went wrong
                    self._matched_files.append(s_file)

                # skips file if insufficient entires
                except InsufficientEntriesError:
                    self._skipped += 1

                # adds file to failed if error occurs
                except InvalidFileNameError as error_msg:
                    s_file.set_message(
                        f"{'-- FAILED  --':15}\"{s_file.name}\"\n" +
                        f"{'   Reason:':15}Invalid File: {error_msg}\n")
                    self._failed_files.append(s_file)
                    continue
                except InvalidMatchError as error_msg:
                    s_file.set_message(
                        f"{'-- FAILED  --':15}\"{s_file.name}\"\n" +
                        f"{'   Reason:':15}Invalid Match: {error_msg}\n")
                    self._failed_files.append(s_file)
                    continue
                except:
                    print("Unexpected error. Stopping operation:")
                    input("\npress ENTER to dismiss...\n")
                    logging.exception("Unexpected Error")
                    exit()

        logging.info(f"{self._total_files} scanned, " +
            f"{len(self._matched_files)} matched, "+
            f"{len(self._failed_files)} failed, {self._skipped} skipped.")

    # prints results from run_matches
    def print_matches(self):

        for f in self._matched_files:
            print(f.message)

        for f in self._failed_files:
            print(f.message)

        print("-" * 80)
        print(f"SUCCESSFULLY MATCHED: {len(self._matched_files)} file(s)")
        print(f"FAILED TO MATCH     : {len(self._failed_files)} file(s)")


        if self._skipped:
            field_names = []
            for field_dict in self._fields_config:
                for key in field_dict:
                    field_names.append(key)
            fn_format = ' - '.join(map(
                lambda s: '['+s+']', field_names))
            print(f"\nSkipped {self._skipped} file(s) due to " +
                f"insufficient field entires.\nRequired format: {fn_format}")

        print("-" * 80)

    # finally transfers files to target path
    def run_transfers(self):

        # end operation if there are no files to transfer
        if not self._matched_files:
            print("\n\nNo files to transfer. Stopping opertation.")
            input("press ENTER to dismiss...\n>>> ")
            exit()


        # confirms file transfers
        resp = input(f"\n\nProceed with transfering the " +
                     f"{len(self._matched_files)}" +
                     " files(s)? (y for YES | n for NO)\n>>> ").strip().lower()

        while resp not in ("y", "n"):
            resp = input("Invalid input, please enter y or n\n>>> ").strip().lower()

        if resp == "y":
            print("\nStarting File Transfer...")
        elif resp == "n":
            print("\nStopping opertation.")
            input("press ENTER to dismiss...\n>>> ")
            exit()

        # tranfers files
        transfered = 0
        for file in self._matched_files:
            try:
                # rename(file.path, file.target_path)
                print(f"{file.name+'  ':.<74} DONE")
                transfered += 1
            except:
                print(f"{file.name+'  ':.<74} FAILED!")
                logging.exception(f"File transfer failed on file: {file.name}")
            else:
                logging.info(
                    "transfered successfully:"+
                    f"\n    filename: \"{file.name}\"" +
                    f"\n    from:     \"{file.directory}\"" +
                    f"\n    to:       \"{file.target_sub_dir}\"")


        print("-" * 80)
        print(f"TRANSFERED: {transfered} file(s)")
        print("-" * 80)

        input("\n\npress ENTER to dismiss...\n>>> ")



if __name__ == "__main__":

    logging.basicConfig(
        filename="auto_filer.log",
        level=logging.INFO,
        format=f"%(asctime)s : %(levelname)s : {getpass.getuser()} : %(funcName)s : %(message)s")
    try:
        logging.info(f"file transfer program ran from user: {getpass.getuser()}")
        autofiler = AutoFile()
        autofiler.parse_config("auto_filer_config.yml")
        autofiler.run_matches()
        autofiler.print_matches()
        autofiler.run_transfers()
    except SystemExit:
        logging.info("System Exit")
    except:
        logging.exception("Unexpected Error:")
        print("Unexpected error. Stopping operation:")
        input("press ENTER to dismiss...\n>>> ")
    finally:
        logging.info(f"file transfer program ended\n")


