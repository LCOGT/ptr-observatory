import os
import importlib.util
import argparse
from itertools import combinations

def dict_diff(dict1, dict2, path=""):
    """
    Identify differences in keys between two dictionaries, including nested dictionaries.

    Args:
        dict1 (dict): First dictionary
        dict2 (dict): Second dictionary
        path (str): Current key path (used for recursion)

    Returns:
        tuple: Two sets containing keys unique to dict1 and dict2 respectively,
              with nested keys represented as paths from the root
    """
    unique_to_dict1 = set()
    unique_to_dict2 = set()

    # Find keys in dict1 that are not in dict2 or have different types
    for key in dict1:
        current_path = f"{path}.{key}" if path else key

        if key not in dict2:
            unique_to_dict1.add(current_path)
        elif isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
            # Recursively check nested dictionaries
            nested_diff1, nested_diff2 = dict_diff(dict1[key], dict2[key], current_path)
            unique_to_dict1.update(nested_diff1)
            unique_to_dict2.update(nested_diff2)
        elif isinstance(dict1[key], dict) != isinstance(dict2[key], dict):
            # If one is a dict and the other isn't, mark as different
            unique_to_dict1.add(current_path)
            unique_to_dict2.add(current_path)

    # Find keys in dict2 that are not in dict1
    for key in dict2:
        current_path = f"{path}.{key}" if path else key
        if key not in dict1:
            unique_to_dict2.add(current_path)

    return unique_to_dict1, unique_to_dict2


def load_all_site_configs():
    """
    Load all site configuration files from configs/<site_name>/obs_config.py
    and return a dictionary of site_name -> site_config
    """
    site_configs = {}
    configs_dir = os.path.join(os.path.dirname(__file__), 'configs')

    # Get all subdirectories in configs/
    for site_name in os.listdir(configs_dir):
        site_dir = os.path.join(configs_dir, site_name)

        # Skip if not a directory or if it's the RETIRED directory
        if not os.path.isdir(site_dir) or site_name == 'RETIRED':
            continue

        config_file = os.path.join(site_dir, 'obs_config.py')

        # Skip if obs_config.py doesn't exist
        if not os.path.isfile(config_file):
            continue

        try:
            # Dynamically import the module
            spec = importlib.util.spec_from_file_location(f"{site_name}_config", config_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Extract site_config from the module
            if hasattr(module, 'site_config'):
                site_configs[site_name] = module.site_config
            else:
                print(f"Warning: {site_name}/obs_config.py exists but doesn't have a site_config variable")
        except Exception as e:
            print(f"Error loading {site_name}/obs_config.py: {str(e)}")

    return site_configs

def get_default_site():
    """
    Determines the default site based on the hostname file in the parent directory.

    The default site is determined by looking for a file in the parent directory
    with the pattern 'hostname{site}'. For example, if the file 'hostnametbo2'
    exists, the default site would be 'tbo2'.

    Returns:
        str: The default site name, or None if no hostname file is found.
    """
    # Get the parent directory path
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Look for files matching the hostname pattern
    hostname_pattern = "hostname"
    for file in os.listdir(parent_dir):
        if file.startswith(hostname_pattern):
            # Extract the site name from the hostname file
            site = file[len(hostname_pattern):]
            return site

    # No hostname file found
    return None

def print_missing_keys(current_site, reference_site, unique_to_current, unique_to_reference):
    """
    Print keys that exist in the reference site but are missing from the current site.

    Args:
        current_site (str): Name of the current site
        reference_site (str): Name of the reference site
        unique_to_current (set): Set of keys unique to the current site
        unique_to_reference (set): Set of keys unique to the reference site
    """
    if not unique_to_reference:
        print(f"\n{current_site} has all keys present in {reference_site}.")
        return

    print(f"\nKeys in {reference_site} missing from {current_site}:")
    for key in sorted(unique_to_reference):
        print(f"  - {key}")
    print(f"Total: {len(unique_to_reference)} missing keys")

if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Compare site configurations')
    parser.add_argument('-r', '--reference', default='eco1',
                        help='Reference site to compare against (default: eco1)')
    args = parser.parse_args()

    all_configs = load_all_site_configs()
    this_site = get_default_site()

    # Check if the reference site exists
    if args.reference not in all_configs:
        print(f"Error: Reference site '{args.reference}' not found")
        print(f"Available sites: {', '.join(all_configs.keys())}")
        exit(1)

    current_site_config = all_configs[this_site]
    reference_site_config = all_configs[args.reference]

    unique_to_current, unique_to_reference = dict_diff(current_site_config, reference_site_config)

    print(f"Comparing {this_site} (current) with {args.reference} (reference)")
    print_missing_keys(this_site, args.reference, unique_to_current, unique_to_reference)