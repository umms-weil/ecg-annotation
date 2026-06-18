#!/usr/bin/env python3

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import pandas as pd


logger = logging.getLogger("ehr_event_processing")


def setup_logging(config: dict):
    log_level_str = config.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logger.setLevel(log_level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file = config.get("log_file")
    if log_file:
        log_file_path = Path(log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info(f"Logging to file: {log_file_path}")

    logger.info(f"Logging initialized at level: {logging.getLevelName(log_level)}")


def safe_path_component(value: str) -> str:
    value = str(value).strip()
    value = re.sub(r"[^\w.\-]+", "_", value)
    return value or "UNKNOWN"


def detect_column(df: pd.DataFrame, aliases, required_name: str) -> str:
    columns = list(df.columns)

    for alias in aliases:
        if alias in columns:
            logger.debug(f"Detected {required_name} column by exact match: {alias}")
            return alias

    lower_map = {str(c).lower(): c for c in columns}
    for alias in aliases:
        alias_lower = str(alias).lower()
        if alias_lower in lower_map:
            detected = lower_map[alias_lower]
            logger.debug(
                f"Detected {required_name} column by case-insensitive match: {detected}"
            )
            return detected

    raise ValueError(
        f"Could not detect {required_name} column. "
        f"Tried aliases: {aliases}. Available columns: {columns}"
    )


def read_table(file_cfg: dict) -> pd.DataFrame:
    path = Path(file_cfg["path"])
    suffix = path.suffix.lower()

    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    logger.info(f"Reading file: {path}")

    if suffix == ".csv":
        sep = file_cfg.get("sep", ",")
        df = pd.read_csv(path, dtype=str, sep=sep)
        logger.info(f"Read CSV with shape: {df.shape[0]:,} rows x {df.shape[1]:,} columns")
        return df

    if suffix == ".tsv":
        sep = file_cfg.get("sep", "\t")
        df = pd.read_csv(path, dtype=str, sep=sep)
        logger.info(f"Read TSV with shape: {df.shape[0]:,} rows x {df.shape[1]:,} columns")
        return df

    if suffix in [".xlsx", ".xls"]:
        sheet_name = file_cfg.get("sheet_name", 0)
        df = pd.read_excel(path, sheet_name=sheet_name, dtype=str)
        logger.info(
            f"Read Excel sheet={sheet_name} with shape: "
            f"{df.shape[0]:,} rows x {df.shape[1]:,} columns"
        )
        return df

    if suffix == ".parquet":
        df = pd.read_parquet(path)
        logger.info(
            f"Read Parquet with shape: {df.shape[0]:,} rows x {df.shape[1]:,} columns"
        )
        return df

    raise ValueError(
        f"Unsupported file type for {path}. "
        f"Supported: .csv, .tsv, .xlsx, .xls, .parquet"
    )


def normalize_one_file(file_cfg: dict, config: dict) -> pd.DataFrame:
    path = Path(file_cfg["path"])
    source_table = file_cfg.get("source_table", path.stem)

    logger.info("-" * 80)
    logger.info("Starting file normalization")
    logger.info(f"Source table: {source_table}")
    logger.info(f"Input file: {path}")

    df = read_table(file_cfg)

    original_row_count = len(df)

    if original_row_count == 0:
        logger.warning(f"Input file has zero rows: {path}")

    df.columns = [str(c).strip() for c in df.columns]

    logger.debug(f"Columns in file {path}: {list(df.columns)}")

    if "mrn_col" in file_cfg:
        mrn_col = file_cfg["mrn_col"]
        if mrn_col not in df.columns:
            raise ValueError(
                f"Configured MRN column '{mrn_col}' not found in {path}. "
                f"Available columns: {list(df.columns)}"
            )
        logger.info(f"Using configured MRN column: {mrn_col}")
    else:
        mrn_col = detect_column(
            df,
            config.get("global_mrn_aliases", ["MRN", "mrn"]),
            "MRN"
        )
        logger.info(f"Detected MRN column: {mrn_col}")

    if "csn_col" in file_cfg:
        csn_col = file_cfg["csn_col"]
        if csn_col not in df.columns:
            raise ValueError(
                f"Configured CSN column '{csn_col}' not found in {path}. "
                f"Available columns: {list(df.columns)}"
            )
        logger.info(f"Using configured CSN column: {csn_col}")
    else:
        csn_col = detect_column(
            df,
            config.get("global_csn_aliases", ["CSN", "csn"]),
            "CSN"
        )
        logger.info(f"Detected CSN column: {csn_col}")

    event_time_col = file_cfg["event_time_col"]

    if event_time_col not in df.columns:
        raise ValueError(
            f"Event time column '{event_time_col}' not found in {path}. "
            f"Available columns: {list(df.columns)}"
        )

    logger.info(f"Using event time column: {event_time_col}")

    df["MRN"] = df[mrn_col].astype(str).str.strip()
    df["CSN"] = df[csn_col].astype(str).str.strip()

    df["original_event_time"] = df[event_time_col]

    date_format = file_cfg.get("date_format")

    if date_format:
        logger.info(f"Parsing event times using configured date format: {date_format}")
        df["event_time"] = pd.to_datetime(
            df[event_time_col],
            format=date_format,
            errors="coerce"
        )
    else:
        logger.info("Parsing event times using pandas automatic parser")
        df["event_time"] = pd.to_datetime(
            df[event_time_col],
            errors="coerce"
        )

    n_bad_times = df["event_time"].isna().sum()
    if n_bad_times > 0:
        logger.warning(
            f"{n_bad_times:,} rows in {path.name} have missing or unparseable event_time"
        )

    timezone = file_cfg.get("timezone", config.get("timezone"))
    if timezone:
        logger.info(f"Applying timezone localization: {timezone}")
        try:
            df["event_time"] = df["event_time"].dt.tz_localize(
                timezone,
                nonexistent="NaT",
                ambiguous="NaT"
            )
        except TypeError:
            logger.warning(
                "Timezone localization was skipped because timestamps may already "
                "be timezone-aware or mixed."
            )

    df["source_table"] = source_table
    df["source_file"] = str(path)
    df["original_event_time_col"] = event_time_col

    missing_mrn = (
        df["MRN"].isna() |
        (df["MRN"].astype(str).str.strip() == "") |
        (df["MRN"].astype(str).str.lower() == "nan")
    ).sum()

    missing_csn = (
        df["CSN"].isna() |
        (df["CSN"].astype(str).str.strip() == "") |
        (df["CSN"].astype(str).str.lower() == "nan")
    ).sum()

    if missing_mrn > 0:
        logger.warning(f"{missing_mrn:,} rows in {path.name} have missing MRN")

    if missing_csn > 0:
        logger.warning(f"{missing_csn:,} rows in {path.name} have missing CSN")

    if config.get("drop_rows_missing_ids_or_time", True):
        before = len(df)

        df = df.dropna(subset=["MRN", "CSN", "event_time"])
        df = df[
            (df["MRN"].astype(str).str.strip() != "") &
            (df["CSN"].astype(str).str.strip() != "") &
            (df["MRN"].astype(str).str.lower() != "nan") &
            (df["CSN"].astype(str).str.lower() != "nan")
        ]

        after = len(df)
        dropped = before - after

        if dropped > 0:
            logger.warning(
                f"Dropped {dropped:,} rows from {path.name} due to missing "
                f"MRN, CSN, or event_time"
            )
        else:
            logger.info("No rows dropped for missing MRN, CSN, or event_time")

    unique_mrns = df["MRN"].nunique(dropna=True)
    unique_csns = df["CSN"].nunique(dropna=True)

    logger.info(f"Valid rows after normalization: {len(df):,}")
    logger.info(f"Unique MRNs in file: {unique_mrns:,}")
    logger.info(f"Unique CSNs in file: {unique_csns:,}")

    if len(df) > 0:
        logger.info(f"Earliest event time in file: {df['event_time'].min()}")
        logger.info(f"Latest event time in file: {df['event_time'].max()}")

    key_cols = [
        "MRN",
        "CSN",
        "event_time",
        "source_table",
        "source_file",
        "original_event_time_col",
        "original_event_time"
    ]

    other_cols = [c for c in df.columns if c not in key_cols]
    df = df[key_cols + other_cols]

    logger.info(f"Finished file normalization: {path.name}")

    return df


def build_output_path(
    base_output_dir: Path,
    folder_template: str,
    mrn: str,
    csn: str,
    output_filename: str
) -> Path:
    safe_mrn = safe_path_component(mrn)
    safe_csn = safe_path_component(csn)

    relative_folder = folder_template.format(
        MRN=safe_mrn,
        CSN=safe_csn
    )

    return base_output_dir / relative_folder / output_filename


def validate_output_plan(
    combined: pd.DataFrame,
    base_output_dir: Path,
    folder_template: str,
    output_filename: str,
    require_existing_encounter_folders: bool,
    dry_run: bool
) -> pd.DataFrame:
    logger.info("-" * 80)
    logger.info("Building per-encounter output plan")

    manifest_rows = []

    grouped = combined.groupby(["MRN", "CSN"], dropna=False, sort=True)
    n_groups = grouped.ngroups

    logger.info(f"Number of encounter groups in output plan: {n_groups:,}")

    for group_idx, ((mrn, csn), group) in enumerate(grouped, start=1):
        output_path = build_output_path(
            base_output_dir=base_output_dir,
            folder_template=folder_template,
            mrn=mrn,
            csn=csn,
            output_filename=output_filename
        )

        output_folder = output_path.parent
        folder_exists = output_folder.exists()

        manifest_rows.append({
            "MRN": mrn,
            "CSN": csn,
            "n_events": len(group),
            "first_event_time": group["event_time"].min(),
            "last_event_time": group["event_time"].max(),
            "output_folder": str(output_folder),
            "output_path": str(output_path),
            "output_folder_exists": folder_exists
        })

    output_plan = pd.DataFrame(manifest_rows)

    if output_plan.empty:
        logger.warning("Output plan is empty. No encounter files would be written.")
        return output_plan

    duplicated_paths = output_plan["output_path"].duplicated(keep=False).sum()

    if duplicated_paths > 0:
        logger.error(
            f"Detected {duplicated_paths:,} output path collisions after path sanitization. "
            "This means multiple MRN/CSN groups would write to the same output file."
        )
        raise RuntimeError(
            "Output path collisions detected. Review MRN/CSN values and folder_template."
        )

    logger.info("No output path collisions detected")

    existing_folders = output_plan["output_folder_exists"].sum()
    missing_folders = len(output_plan) - existing_folders

    logger.info(f"Encounter folders already existing: {existing_folders:,}")
    logger.info(f"Encounter folders missing: {missing_folders:,}")

    if require_existing_encounter_folders and missing_folders > 0:
        logger.error(
            f"{missing_folders:,} encounter folders are missing, and "
            "require_existing_encounter_folders=true."
        )
        raise RuntimeError(
            "Missing required encounter folders. Review base_output_dir/folder_template."
        )

    if dry_run:
        logger.info("Dry run active: no output folders or event files will be created")
    else:
        if missing_folders > 0:
            logger.info(
                "Missing encounter folders will be created during file-writing step"
            )

    logger.info("Finished building output plan")

    return output_plan


def main():
    parser = argparse.ArgumentParser(
        description="Combine multiple EHR event files and write sorted per-encounter event files."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to JSON config file."
    )
    parser.add_argument(
        "--write-combined",
        action="store_true",
        help="Also write a combined_all_events.csv file to the base output directory."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate processing and output paths without writing any files."
    )
    args = parser.parse_args()

    config_path = Path(args.config)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    logger.info(f"Loading config file: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config file: {config_path}")
        logger.exception(e)
        raise

    setup_logging(config)

    logger.info("=" * 80)
    logger.info("Starting EHR event processing")
    logger.info("=" * 80)

    logger.warning(
        "This process may handle PHI. Ensure input files, output files, and logs "
        "are stored only in approved secure locations."
    )

    base_output_dir = Path(config["base_output_dir"])
    folder_template = config.get("folder_template", "{MRN}/{CSN}")
    output_filename = config.get("output_filename", "ehr_events.csv")

    dry_run = bool(config.get("dry_run", False) or args.dry_run)
    require_existing_encounter_folders = bool(
        config.get("require_existing_encounter_folders", False)
    )

    logger.info(f"Base output directory: {base_output_dir}")
    logger.info(f"Folder template: {folder_template}")
    logger.info(f"Per-encounter output filename: {output_filename}")
    logger.info(f"Dry run mode: {dry_run}")
    logger.info(
        f"Require existing encounter folders: {require_existing_encounter_folders}"
    )

    if dry_run:
        logger.warning(
            "DRY RUN MODE ENABLED: input files will be read and validated, "
            "but no output files or directories will be created."
        )

        if not base_output_dir.exists():
            logger.warning(
                f"Base output directory does not currently exist: {base_output_dir}"
            )
    else:
        base_output_dir.mkdir(parents=True, exist_ok=True)

    file_configs = config.get("files", [])

    if not file_configs:
        logger.error("No files specified in config under key 'files'")
        raise RuntimeError("No files specified in config under key 'files'")

    logger.info(f"Number of configured input files: {len(file_configs):,}")

    all_dfs = []
    failed_files = []

    for idx, file_cfg in enumerate(file_configs, start=1):
        path = file_cfg.get("path", "UNKNOWN_PATH")

        logger.info(f"Processing file {idx:,} of {len(file_configs):,}: {path}")

        try:
            df = normalize_one_file(file_cfg, config)
            all_dfs.append(df)
        except Exception as e:
            logger.error(f"Failed processing file: {path}")
            logger.exception(e)

            failed_files.append(path)

            if config.get("continue_on_file_error", False):
                logger.warning(
                    "Continuing because continue_on_file_error=true in config"
                )
                continue
            else:
                logger.error(
                    "Stopping because continue_on_file_error is false or not set"
                )
                raise

    if failed_files:
        logger.warning(f"Number of failed files: {len(failed_files):,}")
        for failed_path in failed_files:
            logger.warning(f"Failed file: {failed_path}")

    if not all_dfs:
        logger.error("No input files were successfully loaded.")
        raise RuntimeError("No input files were successfully loaded.")

    logger.info("-" * 80)
    logger.info("Combining normalized dataframes")

    combined = pd.concat(all_dfs, ignore_index=True, sort=False)

    logger.info(f"Combined rows before duplicate handling: {len(combined):,}")
    logger.info(f"Combined columns: {len(combined.columns):,}")

    if config.get("drop_exact_duplicates", False):
        before = len(combined)
        combined = combined.drop_duplicates()
        after = len(combined)
        dropped_dupes = before - after

        if dropped_dupes > 0:
            logger.warning(f"Dropped {dropped_dupes:,} exact duplicate rows")
        else:
            logger.info("No exact duplicate rows found")

    logger.info("Sorting combined events by MRN, CSN, event_time, source_table")

    combined = combined.sort_values(
        by=["MRN", "CSN", "event_time", "source_table"],
        kind="mergesort"
    ).reset_index(drop=True)

    total_rows = len(combined)
    total_mrns = combined["MRN"].nunique(dropna=True)
    total_csns = combined["CSN"].nunique(dropna=True)

    logger.info(f"Combined row count: {total_rows:,}")
    logger.info(f"Unique MRNs: {total_mrns:,}")
    logger.info(f"Unique CSNs: {total_csns:,}")

    if total_rows > 0:
        logger.info(f"Overall earliest event time: {combined['event_time'].min()}")
        logger.info(f"Overall latest event time: {combined['event_time'].max()}")

    if args.write_combined:
        combined_path = base_output_dir / "combined_all_events.csv"

        if dry_run:
            logger.info(
                f"Dry run active: would write combined file to: {combined_path}"
            )
        else:
            logger.info(f"Writing combined file: {combined_path}")
            combined.to_csv(combined_path, index=False)
            logger.info("Finished writing combined file")

    output_plan = validate_output_plan(
        combined=combined,
        base_output_dir=base_output_dir,
        folder_template=folder_template,
        output_filename=output_filename,
        require_existing_encounter_folders=require_existing_encounter_folders,
        dry_run=dry_run
    )

    if dry_run:
        logger.info("-" * 80)
        logger.info("Dry run summary")
        logger.info(f"Input files successfully loaded: {len(all_dfs):,}")
        logger.info(f"Combined rows after normalization: {len(combined):,}")
        logger.info(f"Unique MRNs: {combined['MRN'].nunique(dropna=True):,}")
        logger.info(f"Unique CSNs: {combined['CSN'].nunique(dropna=True):,}")
        logger.info(f"Encounter files that would be written: {len(output_plan):,}")

        if len(output_plan) > 0:
            logger.info(
                f"Total event rows that would be distributed: "
                f"{output_plan['n_events'].sum():,}"
            )
            logger.info(
                f"Smallest encounter event count: {output_plan['n_events'].min():,}"
            )
            logger.info(
                f"Largest encounter event count: {output_plan['n_events'].max():,}"
            )

        logger.info("Dry run completed successfully. No files were written.")
        logger.info("=" * 80)
        logger.info("Done")
        logger.info("=" * 80)
        return

    logger.info("-" * 80)
    logger.info("Writing per-encounter event files")

    manifest_rows = []

    grouped = combined.groupby(["MRN", "CSN"], dropna=False, sort=True)
    n_groups = grouped.ngroups

    logger.info(f"Number of encounter groups to write: {n_groups:,}")

    write_progress_interval = int(config.get("write_progress_interval", 100))
    written_count = 0

    for group_idx, ((mrn, csn), group) in enumerate(grouped, start=1):
        output_path = build_output_path(
            base_output_dir=base_output_dir,
            folder_template=folder_template,
            mrn=mrn,
            csn=csn,
            output_filename=output_filename
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        group = group.sort_values(
            by=["event_time", "source_table"],
            kind="mergesort"
        )

        try:
            group.to_csv(output_path, index=False)
        except Exception as e:
            logger.error(f"Failed to write per-encounter file: {output_path}")
            logger.exception(e)
            raise

        written_count += 1

        manifest_rows.append({
            "MRN": mrn,
            "CSN": csn,
            "n_events": len(group),
            "first_event_time": group["event_time"].min(),
            "last_event_time": group["event_time"].max(),
            "output_path": str(output_path)
        })

        if (
            written_count == 1 or
            written_count == n_groups or
            written_count % write_progress_interval == 0
        ):
            logger.info(
                f"Wrote {written_count:,} of {n_groups:,} encounter files"
            )

    manifest = pd.DataFrame(manifest_rows)
    manifest_path = base_output_dir / "ehr_event_file_manifest.csv"

    logger.info(f"Writing manifest file: {manifest_path}")
    manifest.to_csv(manifest_path, index=False)

    logger.info("-" * 80)
    logger.info(f"Wrote {written_count:,} per-encounter files")
    logger.info(f"Wrote manifest: {manifest_path}")

    if failed_files:
        logger.warning(
            "Processing completed with one or more failed input files. "
            "Review log warnings/errors."
        )
    else:
        logger.info("Processing completed successfully with no failed input files")

    logger.info("=" * 80)
    logger.info("Done")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()