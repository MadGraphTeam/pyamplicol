#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Drive the M-QCD reference campaign (``mqcd_campaign.json``).

Every run of the campaign is one MadLoop reference: a process of
``required_processes.json``, an export (its own, under
``$LOOP_REFERENCE_ROOT/runs/mqcd/<process>/madloop-export``, or another row's),
a points file and optional per-helicity and second-provider runs. Work
directories are ``$LOOP_REFERENCE_ROOT/runs/mqcd/<run>/``.

Subcommands (each takes run ids; ``all`` selects every run):

``export``    MadLoop export of a run's own process (``madloop_export.py``).
``points``    the run's points.json (exact, supplied, copied from a run or a fixture).
``run``       MadLoop accurate run (and the per-helicity run, the second provider);
              ``--cpu`` pins it; ``split_points`` runs evaluate one point per job.
``merge``     ``references.py merge`` into reference.json.
``fixture``   copy reference.json to ``tests/fixtures/loop/required/mqcd/<run>.json`` with
              every absolute path rewritten relative to ``${LOOP_REFERENCE_ROOT}``.
``manifest``  write ``tests/fixtures/loop/required/mqcd_references.json``.
``status``    one line per run.

Nothing here is process-specific: the processes, schemes and points families
come from the JSON files. Each provider job runs under ``timeout`` (the
campaign's ``job_timeout_seconds``).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent
CAMPAIGN = HERE / "mqcd_campaign.json"
FIXTURES = REPOSITORY / "tests/fixtures/loop"
MANIFEST = FIXTURES / "required/mqcd_references.json"
OLD_ROOTS = ("/shared/external/pyLoopAmpliCol/workspace/reference",)
sys.path.insert(0, str(HERE))
import required_spec  # noqa: E402


def load():
    data = json.loads(CAMPAIGN.read_text())
    return data, {r["id"]: r for r in data["runs"]}


def reference_root(args):
    root = args.reference_root or os.environ.get("LOOP_REFERENCE_ROOT")
    if not root:
        raise SystemExit("set LOOP_REFERENCE_ROOT or pass --reference-root")
    return Path(os.path.abspath(root))


def select(runs, names):
    if names == ["all"]:
        return list(runs.values())
    missing = [n for n in names if n not in runs]
    if missing:
        raise SystemExit(f"unknown runs {missing}")
    return [runs[n] for n in names]


def work_dir(root, run):
    return root / "runs/mqcd" / run["id"]


def python():
    return os.environ.get("LOOP_REFERENCE_PYTHON", sys.executable)


def timeout(data):
    return ["timeout", str(data["madloop_settings"]["job_timeout_seconds"])]


def check_export(root, run):
    """An export another row produced must hold the run's process on its model."""
    export = root / run["export"]
    generation = export.parent / f"{export.name}.generation.json"
    record = json.loads(generation.read_text())
    if record.get("status") != "compiled":
        raise SystemExit(f"{run['id']}: export {export} is not compiled ({record.get('status')})")
    spec = required_spec.load_process(required_spec.DEFAULT_SPEC, run["process"], {"mg5": "", "reference": ""})
    # Only the recorded text is compared (exports made in an old root name it).
    if Path(record["model"]).name != Path(spec["madloop"]["model"]).name:
        raise SystemExit(f"{run['id']}: export model {Path(record['model']).name} is not "
                         f"{Path(spec['madloop']['model']).name}")
    if record["command"] != spec["madloop"]["process"]:
        raise SystemExit(f"{run['id']}: export command {record['command']!r} != {spec['madloop']['process']!r}")
    return export


def command_export(args, data, runs):
    root = reference_root(args)
    for run in select(runs, args.runs):
        export = root / run["export"]
        if export.parent != root / "runs/mqcd" / run["process"] or export.exists():
            print(f"{run['id']}: export {export} exists or belongs to another row; skipped")
            continue
        export.parent.mkdir(parents=True, exist_ok=True)
        log = export.parent / "madloop-export.log"
        with open(log, "w") as handle:
            subprocess.run([*timeout(data), python(), str(HERE / "madloop_export.py"), "--spec",
                            str(required_spec.DEFAULT_SPEC), "--process", run["process"], "--mg5",
                            str(root / "sources/MG5_aMC_v3_7_0"), "--output", str(export),
                            "--compile-jobs", str(args.compile_jobs)],
                           cwd=export.parent, stdout=handle, stderr=subprocess.STDOUT, check=True)


def points_from_fixture(path, pdgs, half_scale_point=False):
    """The points of a committed reference (optionally with a copy of its first
    point at half its scale, the campaign's mu_R = mu_0/2 point)."""
    fixture = json.loads(path.read_text())
    if fixture.get("pdgs", pdgs) != pdgs:
        raise SystemExit(f"{path} belongs to {fixture['pdgs']}, not {pdgs}")
    construction = fixture.get("point_construction", {}).get("construction", "see that fixture")
    def exact_text(x):
        # Integer momenta (older fixtures) convert exactly; refuse floats (lossy).
        if isinstance(x, bool) or not isinstance(x, (str, int)):
            raise SystemExit(f"{path}: momentum component {x!r} is not exact")
        return str(x)

    points = [[[exact_text(x) for x in leg] for leg in point] for point in fixture["points"]]
    out = {"process_name": fixture.get("name"), "pdgs": pdgs, "points": points,
           "mu_r": list(fixture["mu_r"]),
           "construction": f"copied from the committed fixture {path.relative_to(FIXTURES)} ({construction})"}
    if half_scale_point:
        from fractions import Fraction

        from exact_points import decimal_string

        out["points"].append(out["points"][0])
        out["mu_r"].append(decimal_string(Fraction(out["mu_r"][0]) / 2))
        out["scale_variation"] = {"point": len(out["points"]), "copy_of_point": 1, "mu_r_factor": "1/2"}
    return out


def supplied_command(run, target):
    """The supplied_points.py command writing a 'supplied' run's points to ``target``."""
    spec = run["points"]
    options = ["--family", spec.get("family", "regular"), "--count", str(spec.get("count", 3))]
    if spec.get("values"):
        options += ["--values", *spec["values"]]
    if spec.get("madloop_qp_point"):
        options.append("--madloop-qp-point")
    for key in ("rotate", "zero_cosine", "neighbour_cosine"):
        if key in spec:
            options.append(f"--{key.replace('_', '-')}={spec[key]}")  # values may start with '-'
    if spec.get("half_scale_point", True):
        options.append("--half-scale-point")
    return [python(), str(HERE / "supplied_points.py"), "--process", run["process"], "--output", str(target),
            *options]


def command_points(args, data, runs):
    root = reference_root(args)
    for run in select(runs, args.runs):
        work = work_dir(root, run)
        work.mkdir(parents=True, exist_ok=True)
        target = work / "points.json"
        if target.exists() and not args.force:
            print(f"{run['id']}: points exist")
            continue
        spec = run["points"]
        pdgs = run.get("pdgs")
        if spec["generator"] == "fixture":
            ref_spec = required_spec.load_process(required_spec.DEFAULT_SPEC, run["process"])
            target.write_text(json.dumps(points_from_fixture(FIXTURES / spec["fixture"], ref_spec["pdgs"],
                                                             spec.get("half_scale_point", False)), indent=2) + "\n")
        elif spec["generator"] == "run":
            shutil.copyfile(work_dir(root, runs[spec["run"]]) / "points.json", target)
        elif spec["generator"] == "exact":
            subprocess.run([python(), str(HERE / "exact_points.py"), "--process", run["process"], "--output", str(target),
                            "--count", str(spec.get("count", 3)), *(["--half-scale-point"] if spec.get(
                                "half_scale_point", True) else [])], check=True, stdout=subprocess.DEVNULL)
        elif spec["generator"] == "supplied":
            subprocess.run(supplied_command(run, target), check=True, stdout=subprocess.DEVNULL)
        else:
            raise SystemExit(f"unknown points generator {spec['generator']!r}")
        if pdgs:
            points = json.loads(target.read_text())
            if points["pdgs"] != pdgs:
                points["pdgs"] = pdgs  # same masses: one subprocess of a multiparticle export
                target.write_text(json.dumps(points, indent=2) + "\n")
        print(target)


def evaluation(data, run):
    """The run's MadLoop evaluation: the campaign's quadruple-precision
    evaluation (madloop_settings.evaluation) unless the run keeps the
    evaluation of an earlier batch (``madloop_evaluation``)."""
    if run.get("madloop_evaluation", {}).get("mode") == "mlstabthres":
        return None
    return data["madloop_settings"]["evaluation"]


def madloop_jobs(data, run, skip_helicities=False):
    """(label, references.py run options) of every MadLoop job of a run."""
    setting = evaluation(data, run)
    options = []
    if setting is not None:
        options = ["--madloop-accuracy", str(setting["requested_relative_accuracy"]),
                   *(x for key, value in setting["madloop_params"].items()
                     for x in ("--madloop-param", f"{key}={value}"))]
    if setting is not None and setting.get("quadruple_precision_stage"):
        options.append("--madloop-quadruple")
    jobs = [("madloop", options)]
    if run.get("helicities") and not skip_helicities:
        jobs.append(("madloop-hel", ["--tag", "hel", "--helicities", run["helicities"], *options]))
    return jobs


def provider_run(args, data, root, run, work, points, extra, log, cpu):
    export = check_export(root, run)
    command = [*timeout(data), python(), str(HERE / "references.py"), "run", "--process", run["process"],
               "--points", str(points), "--work-dir", str(work), "--reference-root", str(root),
               "--provider", "madloop", "--mg5", str(root / "sources/MG5_aMC_v3_7_0"), "--madloop-export", str(export)]
    if "--madloop-accuracy" not in extra:
        command += ["--madloop-accuracy", str(run.get("madloop_accuracy",
                                                      data["madloop_settings"]["requested_relative_accuracy"]))]
    command += extra
    if run.get("subprocess"):
        command += ["--subprocess", run["subprocess"]]
    if run.get("pdgs"):
        command += ["--pdgs", ",".join(map(str, run["pdgs"]))]
    if cpu is not None:
        command += ["--cpu", str(cpu)]
    with open(log, "w") as handle:
        completed = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
    if completed.returncode:
        raise SystemExit(f"{run['id']}: provider run failed ({completed.returncode}); see {log}")


SPLIT_LABELS = ("madloop",)


def combine_split(work, label, count):
    """Concatenate one-point results (point-<i>/) into <label>-result.json."""
    parts = [json.loads((work / f"point-{i}" / f"{label}-result.json").read_text()) for i in range(1, count + 1)]
    combined = dict(parts[0])
    combined["rows"] = [part["rows"][0] for part in parts]
    combined["points_file"] = str(work / "points.json")
    # Whole-run quantities: summed over the jobs (per-job values below), never point 1's alone.
    combined["process_wall_seconds"] = sum(p["process_wall_seconds"] for p in parts)
    cpus = [p.get("cpu") for p in parts]
    combined["cpu"] = cpus[0] if len(set(cpus)) == 1 else None
    combined["split_points"] = {"jobs": count, "initial_call_seconds": [p.get("initial_call_seconds") for p in parts],
                                "process_wall_seconds": [p["process_wall_seconds"] for p in parts],
                                "cpus": cpus,
                                "note": "one job per point: every point is also the job's initialisation point; "
                                        "process_wall_seconds is the sum over the jobs, initial_call_seconds the "
                                        "first job's (all jobs listed here)"}
    (work / f"{label}-result.json").write_text(json.dumps(combined, indent=2) + "\n")


def command_run(args, data, runs):
    root = reference_root(args)
    for run in select(runs, args.runs):
        work = work_dir(root, run)
        points = work / "points.json"
        if not points.exists():
            raise SystemExit(f"{run['id']}: no points.json")
        jobs = madloop_jobs(data, run, args.skip_helicities)
        if args.only:
            jobs = [job for job in jobs if job[0] in args.only]
        for label, extra in jobs:
            if (work / f"{label}-result.json").exists() and not args.force:
                print(f"{run['id']}: {label} done")
                continue
            if run.get("split_points") and label in SPLIT_LABELS:
                content = json.loads(points.read_text())
                count = len(content["points"])
                if args.point is None:
                    raise SystemExit(f"{run['id']}: split run; pass --point 1..{count} (one job per point), "
                                     "then 'combine'")
                index = args.point
                sub = work / f"point-{index}"
                sub.mkdir(exist_ok=True)
                one = dict(content, points=[content["points"][index - 1]], mu_r=[content["mu_r"][index - 1]])
                (sub / "points.json").write_text(json.dumps(one, indent=2) + "\n")
                provider_run(args, data, root, run, sub, sub / "points.json", extra, sub / f"{label}.log", args.cpu)
                print(sub / f"{label}-result.json")
                continue
            provider_run(args, data, root, run, work, points, extra, work / f"{label}.log", args.cpu)
            print(work / f"{label}-result.json")
        for provider in run.get("second_providers", []):
            if args.skip_second or (args.only and provider not in args.only):
                continue
            if (work / f"{provider}-result.json").exists() and not args.force:
                print(f"{run['id']}: {provider} done")
                continue
            command = [*timeout(data), python(), str(HERE / "references.py"), "run", "--process", run["process"],
                       "--points", str(points), "--work-dir", str(work), "--reference-root", str(root),
                       "--provider", provider, "--recola", str(root / "sources/recola2-2.3.0"),
                       "--openloops", str(root / "sources/OpenLoops-2.1.5")]
            if args.cpu is not None:
                command += ["--cpu", str(args.cpu)]
            with open(work / f"{provider}.log", "w") as handle:
                completed = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
            if completed.returncode:
                raise SystemExit(f"{run['id']}: {provider} failed ({completed.returncode}); see {work / (provider + '.log')}")


def command_combine(args, data, runs):
    root = reference_root(args)
    for run in select(runs, args.runs):
        if not run.get("split_points"):
            continue
        work = work_dir(root, run)
        count = len(json.loads((work / "points.json").read_text())["points"])
        for label in SPLIT_LABELS:
            combine_split(work, label, count)
            print(work / f"{label}-result.json")


def command_merge(args, data, runs):
    root = reference_root(args)
    for run in select(runs, args.runs):
        work = work_dir(root, run)
        command = [python(), str(HERE / "references.py"), "merge", "--process", run["process"], "--points",
                   str(work / "points.json"), "--work-dir", str(work), "--output", str(work / "reference.json")]
        if run.get("pdgs"):
            command += ["--pdgs", ",".join(map(str, run["pdgs"]))]
        for provider, reason in run.get("exclude_providers", {}).items():
            command += ["--exclude", f"{provider}={reason}"]
        if run.get("point_status"):
            command += ["--point-status", json.dumps(run["point_status"])]
        completed = subprocess.run(command, capture_output=True, text=True)
        print(completed.stdout.strip() or completed.stderr.strip()[-400:])
        # exit status 2 = fewer than two providers (single-provider reference): expected.
        if completed.returncode not in (0, 2):
            raise SystemExit(f"{run['id']}: merge failed")


def relocate(value, root):
    """Rewrite absolute reference-root paths (current and old roots, by text
    only: an old root is never opened) to ``${LOOP_REFERENCE_ROOT}``, and the
    repository to ``${REPOSITORY}``."""
    if isinstance(value, dict):
        return {k: relocate(v, root) for k, v in value.items()}
    if isinstance(value, list):
        return [relocate(v, root) for v in value]
    if isinstance(value, str):
        for prefix in (str(root), *OLD_ROOTS):
            value = value.replace(prefix, "${LOOP_REFERENCE_ROOT}")
        return value.replace(str(REPOSITORY), "${REPOSITORY}")
    return value


# Host paths a relocated fixture may not contain (compiler wrappers of the Nix store excepted).
ABSOLUTE = re.compile(r"(?<![\w$}])/(shared|home|tmp|nix/store/[0-9a-z]{32}-(?!gcc|gfortran))\S{0,40}")
TOLERANCE_SCOPE = ("'tolerance' and 'validation_status' are the references.py merge's provider-agreement check "
                   "(the G1 2e-8 tolerance); they are not M-QCD acceptance values: m-qcd/PLAN.md §1.4 applies, with "
                   "each point's 'reference' record")


def command_fixture(args, data, runs):
    root = reference_root(args)
    for run in select(runs, args.runs):
        source = work_dir(root, run) / "reference.json"
        if not source.exists():
            print(f"{run['id']}: no reference.json")
            continue
        content = relocate(json.loads(source.read_text()), root)
        content["tolerance_scope"] = TOLERANCE_SCOPE
        content["mqcd_run"] = {k: run[k] for k in run if k != "points"}
        content["mqcd_run"]["points"] = run["points"]
        text = json.dumps(content, indent=1) + "\n"
        leftover = sorted({m.group(0) for m in ABSOLUTE.finditer(text)})
        if leftover:
            raise SystemExit(f"{run['id']}: absolute paths remain after relocation: {leftover[:5]}")
        target = FIXTURES / "required/mqcd" / f"{run['id']}.json"
        if target.exists() and json.loads(target.read_text()).get("mqcd_run", {}).get("id") != run["id"]:
            raise SystemExit(f"{run['id']}: {target} is another reference; refusing to overwrite it")
        target.write_text(text)
        print(target.relative_to(REPOSITORY))


def sector_accuracy(fixture):
    """Per point and loop sector: MadLoop's accuracy estimate (None when the
    fixture's MadLoop run printed only the requested sector)."""
    out = []
    for row in fixture["rows"]:
        if "sectors" in row:
            out.append({f"QCD^2={s['QCD']},QED^2={s['QED']}": s["accuracy"] for s in row["sectors"]["loop"]})
        else:
            accuracy = row.get("providers", {}).get("madloop", {}).get("accuracy")
            orders = fixture.get("loop_orders"), fixture.get("born_orders")
            key = None
            if all(orders):
                key = (f"QCD^2={orders[1]['QCD'] + orders[0]['QCD']},"
                       f"QED^2={orders[1]['QED'] + orders[0]['QED']}")
            out.append({key: accuracy} if key and accuracy is not None else {})
    return out


def second_provider_outcome(fixture, providers):
    """Per second provider and point: the strict relative difference of each
    coefficient from MadLoop's (the fixture's provider pair record)."""
    out = {}
    for provider in providers:
        pair = f"madloop-{provider}"
        out[provider] = [row["provider_pair_strict_relative_errors"].get(pair) for row in fixture["rows"]]
    return out


def superseded_deviation(fixture):
    """Per point: the largest deviation of the batch-2 MadLoop values (secondary
    run 'mlstabthres') from the reference, per coefficient (references.py merge's
    relative_deviation_from_reference_run: Laurent coefficients with the loop-unit floor)."""
    run = fixture["providers"]["madloop"].get("secondary_runs", {}).get("mlstabthres")
    return None if run is None else run["relative_deviation_from_reference_run"]


def run_entry(root, run, fixture_path):
    entry = {"run": run["id"], "fixture": str(fixture_path.relative_to(FIXTURES)) if fixture_path.exists() else None,
             "process_key": run["process"], "note": run.get("note"),
             "reference_notes": run.get("reference_notes", {}),
             "excluded_providers": run.get("exclude_providers", {}),
             "second_providers": run.get("second_providers", []),
             "second_provider_trigger": run.get("second_provider_trigger")}
    if not fixture_path.exists():
        entry["status"] = "pending"
        return entry
    fixture = json.loads(fixture_path.read_text())
    entry.update({
        "status": "committed",
        "madloop_process": fixture["process"],
        "pdgs": fixture["pdgs"],
        "born_orders": fixture["born_orders"],
        "born_orders_all": fixture.get("born_orders_all", [fixture["born_orders"]]),
        "loop_orders": fixture["loop_orders"],
        "scheme": fixture["scheme"],
        "restriction": fixture.get("restriction"),
        "madloop_model": fixture.get("madloop_model"),
        "gauge": fixture.get("gauge"),
        "parameters": fixture["parameters"],
        "fixed_parameters": fixture["fixed_parameters"],
        "parameter_overrides": fixture.get("parameter_overrides", {}),
        "derived_parameters": fixture.get("derived_parameters"),
        "points": len(fixture["points"]),
        "mu_r": fixture["mu_r"],
        "point_family": fixture.get("point_construction", {}).get("family", "exact terminating decimals"),
        "point_labels": fixture.get("point_construction", {}).get("point_labels"),
        "scale_variation": fixture.get("point_construction", {}).get("scale_variation"),
        "primary_provider": fixture["primary_provider"],
        "validated_providers": fixture["validated_providers"],
        "validation_status": fixture["validation_status"],
        "madloop_return_codes": [row.get("madloop_status") for row in fixture["rows"]],
        "madloop_evaluation": run.get("madloop_evaluation", {}).get("mode", "quadruple"),
        "provider_accuracy_per_sector": sector_accuracy(fixture),
        "second_provider_outcome": second_provider_outcome(fixture, run.get("second_providers", [])),
        "batch2_relative_deviation": superseded_deviation(fixture),
        "squared_split_orders": fixture.get("squared_split_orders"),
        "per_helicity": bool(fixture.get("per_helicity")),
        "subprocess": run.get("subprocess"),
        "point_reference": [row["reference"] for row in fixture["rows"]],
        "per_helicity_reference": ([[{"helicity": e["helicity"], **e["reference"]} for e in entries]
                                    for entries in fixture["per_helicity"]["rows"]]
                                   if fixture.get("per_helicity") else None),
    })
    return entry


def command_manifest(args, data, runs):
    root = reference_root(args)
    rows = []
    for row in data["rows"]:
        route = data["restriction_codes"][row["restriction_code"]]
        entry = {**{k: row[k] for k in ("row", "class", "process", "restriction_code", "reference_kind", "tier",
                                        "extras")},
                 "pyamplicol_route": route, "note": row.get("note")}
        entry["references"] = [run_entry(root, runs[r], FIXTURES / "required/mqcd" / f"{r}.json") for r in row["runs"]]
        existing = []
        for path in row["existing_fixtures"]:
            item = {"fixture": path, "status": "committed" if (FIXTURES / path).exists() else "pending"}
            if (FIXTURES / path).exists() and path.startswith("required/"):
                fixture = json.loads((FIXTURES / path).read_text())
                if "rows" in fixture and "primary_provider" in fixture:
                    item.update({"primary_provider": fixture["primary_provider"],
                                 "validated_providers": fixture.get("validated_providers"),
                                 "points": len(fixture["points"]), "scheme": fixture.get("scheme"),
                                 "provider_accuracy_per_sector": sector_accuracy(fixture)})
            existing.append(item)
        entry["existing_references"] = existing
        if row.get("primary_provider"):
            entry["primary_provider"] = row["primary_provider"]
        rows.append(entry)
    manifest = {
        "schema": "mqcd-references/1",
        "description": "Reference manifest of the M-QCD campaign (m-qcd/PLAN.md §4.2), written by "
                       "tools/loop_reference/mqcd_campaign.py manifest from mqcd_campaign.json and the committed "
                       "fixtures. Per row: process, pyAmpliCol route (restriction, fixed parameters), reference "
                       "runs (fixture path below tests/fixtures/loop, orders, parameters, points, MadLoop accuracy "
                       "per point and loop squared split order) and existing references. 'pending' marks a "
                       "reference not committed yet. The pyAmpliCol request uses the fixture's parameters and "
                       "fixed_parameters (the MadLoop card values).",
        "conventions": {
            "laurent": "MadLoop/BLHA C_eps = (4 pi)^eps / Gamma(1 - eps); physical couplings; initial spin/colour "
                       "average and final identical-particle factor included",
            "squared_split_orders": "QCD^2, QED^2 = summed g_s and e powers of the interfering amplitudes; a loop "
                                    "sector's born_sector is its orders minus the correction step",
            "madloop_accuracy": "MadLoop's own ACC(i) of SLOOPMATRIX_THRES per point and loop squared split "
                                "order: ONE number over the three Laurent coefficients (madloop_settings."
                                "madloop_accuracy_definition), not a per-coefficient relative accuracy. In the "
                                "quadruple-precision evaluation (madloop_evaluation 'quadruple') 0.0 means its two "
                                "quadruple-precision evaluations (propagators in original and reversed order) "
                                "printed identical binary64 values for all three coefficients; that test does not "
                                "see a systematic error both share (g g > u u~ u u~ points 0, 2, 3: accuracy 0.0, "
                                "reference outliers named in reference_notes)",
            "second_provider_outcome": "per triggered second provider and point: the strict relative difference "
                                       "|a - b| / max(|a|, |b|) of each coefficient from MadLoop's (the outcome of the "
                                       "§4.1 trigger named in second_provider_trigger)",
            "batch2_relative_deviation": "per point and coefficient: how far the batch-2 MadLoop values (MLStabThres "
                                         "1e-13, HelicityFilterLevel 2), which this evaluation supersedes, are from "
                                         "the reference (Laurent coefficients relative to max(|a|, |b|, "
                                         "|Born| alpha/(2 pi)))",
            "per_helicity_reference": "per point and helicity configuration (the fixture's per_helicity rows): "
                                      "status, comparison, absolute_scale, born_source and "
                                      "born_double_pole_relative_mismatch as for point_reference; 'absolute' entries "
                                      "(a vanishing helicity, or one suppressed below the point's binary64 condition: "
                                      "printed Born mismatch above 1e-13) compare against absolute_scale = the "
                                      "point's summed |Born| over the configurations",
            "per_helicity": "MadLoop SLOOPMATRIXHEL_THRES: colour average and identical-particle factor, no "
                            "helicity average; HelConfigs.dat helicity labels",
            "indexing": "rows, points, mu_r, point_labels, point_reference, provider_accuracy_per_sector and "
                        "madloop_return_codes are aligned lists (row i = point i, 0-based); reference_notes and "
                        "point_status keys are 0-based row indices; scale_variation's point and copy_of_point are "
                        "1-based point numbers (mqcd_campaign.py run --point), its row and copy_of_row the 0-based "
                        "rows",
            "point_reference": {
                "status": "'ok': the row is a reference; 'none': no usable provider reference at this point "
                          "(reason given), validate it by internal oracles only",
                "comparison": "'relative': compare per coefficient relative to the reference value; 'absolute': "
                              "a Born-zero point (§4.1 S3), compare |value - reference| against the tolerance times "
                              "absolute_scale = |Born| at row absolute_scale_row (the nearest regular point) for the "
                              "Born, and times absolute_scale alpha/(2 pi) (F_s of §1.4) for the Laurent "
                              "coefficients, never dividing by the vanishing Born",
                "born_source": "which value the row's (and its sectors') 'born' is: 'madloop' = MadLoop's printed "
                               "Born; 'madloop_double_pole_over_universal_factor' = at madloop_qp_point points, "
                               "MadLoop's printed Born is its double-precision Born at the binary64 rounding of the "
                               "point, not at the published point, so the reference Born is its quadruple-precision "
                               "double pole over universal_double_pole_factor (the printed value is kept as "
                               "born_madloop_binary64_input / born_binary64_input)",
                "madloop_point": "the point MadLoop's loop values refer to: the published point (quadruple "
                                 "precision at a madloop_qp_point point), the binary64 rounding of the published "
                                 "point (double precision), or MadLoop's quadruple-precision repair of that rounding "
                                 "(~1e-16 from an exact published point)",
                "born_double_pole_relative_mismatch": "MadLoop's printed Born (double precision at the binary64 "
                                                      "input) against the Born its quadruple-precision double pole "
                                                      "implies. At a regular point both are the same Born to its "
                                                      "binary64 rounding (~1e-16 .. 1e-15): a mismatch above that "
                                                      "scale is a loop defect of the reference, not point "
                                                      "sensitivity (C01 point 1 of batch 2: 4.8e-13 from MadLoop's "
                                                      "helicity filter, Recola's own relation holding to 1e-15), "
                                                      "and the integrity tests refuse it at ok points; at "
                                                      "madloop_qp_point points (S1-S3) it is the binary64 condition "
                                                      "of the limit point, bounded by the family's stated bound",
                "max_sector_double_pole_relative_error": "largest violation of the universal double pole over the "
                                                         "loop squared split orders (MadLoop's printed values, "
                                                         "relative to the point's largest double pole); the merge "
                                                         "refuses ok points above its tolerance, the integrity "
                                                         "tests ok regular points above max(10 x the sector "
                                                         "accuracy, 1e-14). At madloop_qp_point points the "
                                                         "reference Born is the double pole over the factor, so the "
                                                         "relation holds there by construction for every sector "
                                                         "with a Born partner; born_double_pole_relative_mismatch "
                                                         "is the falsifiable quantity",
            },
            "fixture_tolerance": TOLERANCE_SCOPE,
            "madloop_settings": data["madloop_settings"],
        },
        "rows": rows,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
    pending = sum(1 for r in rows for x in r["references"] + r["existing_references"] if x["status"] == "pending")
    print(f"{MANIFEST.relative_to(REPOSITORY)}: {len(rows)} rows, {pending} pending references")


def command_status(args, data, runs):
    root = reference_root(args)
    for run in select(runs, args.runs):
        work = work_dir(root, run)
        export = root / run["export"]
        gen = export.parent / f"{export.name}.generation.json"
        state = json.loads(gen.read_text()).get("status") if gen.exists() else "absent"
        flags = [f"export={state}", f"points={'yes' if (work / 'points.json').exists() else 'no'}"]
        for label in ("madloop", "madloop-hel", "recola", "openloops"):
            if (work / f"{label}-result.json").exists():
                flags.append(f"{label}=done")
        flags.append(f"reference={'yes' if (work / 'reference.json').exists() else 'no'}")
        flags.append(f"fixture={'yes' if (FIXTURES / 'required/mqcd' / (run['id'] + '.json')).exists() else 'no'}")
        print(run["id"], " ".join(flags))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference-root", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "points", "run", "combine", "merge", "fixture", "status"):
        p = sub.add_parser(name)
        p.add_argument("runs", nargs="+")
    sub.add_parser("manifest")
    sub.choices["export"].add_argument("--compile-jobs", type=int, default=4)
    sub.choices["points"].add_argument("--force", action="store_true")
    run = sub.choices["run"]
    run.add_argument("--cpu", type=int)
    run.add_argument("--point", type=int, help="1-based point of a split_points run")
    run.add_argument("--force", action="store_true")
    run.add_argument("--only", nargs="+", choices=("madloop", "madloop-hel", "recola", "openloops"))
    run.add_argument("--skip-helicities", action="store_true")
    run.add_argument("--skip-second", action="store_true")
    args = parser.parse_args()
    data, runs = load()
    if args.command == "manifest":
        args.runs = []
    {"export": command_export, "points": command_points, "run": command_run, "combine": command_combine,
     "merge": command_merge, "fixture": command_fixture, "manifest": command_manifest,
     "status": command_status}[args.command](args, data, runs)


if __name__ == "__main__":
    main()
