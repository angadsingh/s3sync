from pathtools.patterns import match_any_paths

"""config.yaml's include/exclude patterns are implemented using pathtools.match_any_path:
https://github.com/gorakhargosh/pathtools/blob/master/pathtools/patterns.py#L220

which ultimately supports unix glob pattern syntax. you can test your patterns here

these patterns are passed to the watchdog as well as aws cli, which also uses the same syntax:
https://docs.aws.amazon.com/cli/latest/reference/s3/index.html#use-of-exclude-and-include-filters
"""

if __name__ == "__main__":
    print match_any_paths(["./.git/file"],
                           included_patterns=None,
                           excluded_patterns=["*.git/*"],
                           case_sensitive=False)
