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
``relocate``  rewrite the absolute reference-root paths of committed fixtures (paths
              below tests/fixtures/loop) by text, every value unchanged.
``status``    one line per run.

Nothing here is process-specific: the processes, schemes and points families
come from the JSON files. Each provider job runs under ``timeout`` (the
campaign's ``job_timeout_seconds``).

``--campaign <json>`` drives another campaign of the same format (the M-SM one:
``msm_campaign.json``); its ``layout`` names the work directories
(``runs/<name>``), the fixture directory and the manifest (defaults: M-QCD's).
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
# The campaign layout (``layout`` of the campaign JSON; these are M-QCD's).
DEFAULT_CAMPAIGN = CAMPAIGN
DEFAULT_LAYOUT = {"name": "M-QCD", "runs": "runs/mqcd", "fixtures": "required/mqcd",
                  "manifest": "required/mqcd_references.json", "schema": "mqcd-references/2",
                  "plan": "m-qcd/PLAN.md"}
LAYOUT = dict(DEFAULT_LAYOUT)
OLD_ROOTS = ("/shared/external/pyLoopAmpliCol/workspace/reference",)
sys.path.insert(0, str(HERE))
import required_spec  # noqa: E402


def load(path=None):
    """The campaign and its runs by id; sets the layout (work, fixture and
    manifest paths) of the campaign at ``path`` (default: M-QCD's), replacing
    that of any earlier call."""
    global CAMPAIGN, MANIFEST
    CAMPAIGN = Path(path).resolve() if path else DEFAULT_CAMPAIGN
    data = json.loads(CAMPAIGN.read_text())
    LAYOUT.clear()
    LAYOUT.update(DEFAULT_LAYOUT, **data.get("layout", {}))
    MANIFEST = FIXTURES / LAYOUT["manifest"]
    return data, {r["id"]: r for r in data["runs"]}


def fixture_path(run_id):
    return FIXTURES / LAYOUT["fixtures"] / f"{run_id}.json"


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
    return root / LAYOUT["runs"] / run["id"]


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
        if export.parent != root / LAYOUT["runs"] / run["process"] or export.exists():
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
    if spec.get("sqrt_s"):
        options += ["--sqrt-s", *spec["sqrt_s"]]
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
        params = {**setting["madloop_params"], **run.get("madloop_params", {})}
        options = ["--madloop-accuracy", str(setting["requested_relative_accuracy"]),
                   *(x for key, value in params.items() for x in ("--madloop-param", f"{key}={value}"))]
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


def tolerance_scope():
    return TOLERANCE_SCOPE.replace("M-QCD", LAYOUT["name"]).replace("m-qcd/PLAN.md", LAYOUT["plan"])


def command_fixture(args, data, runs):
    root = reference_root(args)
    for run in select(runs, args.runs):
        source = work_dir(root, run) / "reference.json"
        if not source.exists():
            print(f"{run['id']}: no reference.json")
            continue
        content = relocate(json.loads(source.read_text()), root)
        content["tolerance_scope"] = tolerance_scope()
        if LAYOUT.get("r2_couplings"):
            # The R2 couplings the MadLoop export calls (m-sm/PLAN.md §1.4, rule-1 R2 correction).
            import references

            spec = required_spec.load_process(required_spec.DEFAULT_SPEC, run["process"],
                                              {"mg5": root / "sources/MG5_aMC_v3_7_0", "reference": root})
            content["madloop_r2_couplings"] = references.madloop_r2_couplings(
                root / run["export"], spec["madloop"]["model"], run.get("subprocess"))
        if run.get("export_parameters"):
            # Model parameters of the export at the run's card per mu_R (madloop_parameters.py).
            record = json.loads((work_dir(root, run) / "export_parameters.json").read_text())
            if set(record["values"]) != set(run["export_parameters"]) or record["mu_r"] != [
                    str(m) for m in content["mu_r"]]:
                raise SystemExit(f"{run['id']}: export_parameters.json does not hold {run['export_parameters']} "
                                 "at the fixture's mu_r")
            content["export_parameters"] = record
        content["mqcd_run"] = {k: run[k] for k in run if k != "points"}
        content["mqcd_run"]["points"] = run["points"]
        text = json.dumps(content, indent=1) + "\n"
        leftover = sorted({m.group(0) for m in ABSOLUTE.finditer(text)})
        if leftover:
            raise SystemExit(f"{run['id']}: absolute paths remain after relocation: {leftover[:5]}")
        target = fixture_path(run["id"])
        if target.exists() and json.loads(target.read_text()).get("mqcd_run", {}).get("id") != run["id"]:
            raise SystemExit(f"{run['id']}: {target} is another reference; refusing to overwrite it")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        print(target.relative_to(REPOSITORY))


def leaves(value, path=()):
    """(path, leaf) of every JSON leaf."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from leaves(v, (*path, k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from leaves(v, (*path, i))
    else:
        yield path, value


def command_relocate(args, data, runs):
    """Rewrite the reference-root and repository paths of committed fixtures
    (paths below tests/fixtures/loop) by text, like ``fixture`` does for the
    campaign's own: every number and every non-path byte is unchanged
    (checked leaf by leaf); refuses a fixture with absolute host paths left."""
    root = reference_root(args)
    for name in args.runs:
        path = FIXTURES / name
        text = path.read_text()
        new = text
        for prefix in (str(root), *OLD_ROOTS):
            new = new.replace(prefix, "${LOOP_REFERENCE_ROOT}")
        new = new.replace(str(REPOSITORY), "${REPOSITORY}")
        before, after = list(leaves(json.loads(text))), list(leaves(json.loads(new)))
        if [p for p, _ in before] != [p for p, _ in after] or any(
                a != b and not (isinstance(a, str) and relocate(a, root) == b)
                for (_, a), (_, b) in zip(before, after, strict=True)):
            raise SystemExit(f"{name}: relocation changed more than path text")
        leftover = sorted({m.group(0) for m in ABSOLUTE.finditer(new)})
        if leftover:
            raise SystemExit(f"{name}: absolute paths remain after relocation: {leftover[:5]}")
        if new != text:
            path.write_text(new)
            print(name)


def sector_accuracy(fixture, binding=None):
    """Per point and loop sector: MadLoop's accuracy estimate (None when the
    fixture's MadLoop run printed only the requested sector, or for a point
    that is not binding)."""
    out = []
    for index, row in enumerate(fixture["rows"]):
        if binding is not None and not binding[index]["binding"]:
            out.append(None)
        elif "sectors" in row:
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


def return_codes(fixture):
    """MadLoop's return code per point (None where the fixture records none)."""
    return [row.get("madloop_status", row.get("providers", {}).get("madloop", {}).get("status"))
            for row in fixture["rows"]]


def evaluation_precision(code):
    """MadLoop's arithmetic at a point from its return code 100*H + 10*T + U."""
    if not isinstance(code, int):
        return None
    return {1: "double", 2: "double", 3: "quadruple", 4: "quadruple (unstable)"}.get(code // 100)


def primary_values(fixture, index):
    """The reference values (born and Laurent coefficients) of a fixture's point."""
    row = fixture["rows"][index]
    if "born" in row:
        return row
    providers = row["providers"]
    return providers.get(fixture.get("primary_provider", "madloop"), next(iter(providers.values())))


def strict(a, b):
    scale = max(abs(a), abs(b))
    return 0.0 if scale == 0 else abs(a - b) / scale


def same_points(a, b):
    """Two fixtures' points and scales (exact decimal text) are the same."""
    from fractions import Fraction

    return ([[str(x) for x in leg] for leg in a[0]] == [[str(x) for x in leg] for leg in b[0]]
            and Fraction(str(a[1])) == Fraction(str(b[1])))


def is_provider_reference(fixture):
    rows = fixture.get("rows")
    return (isinstance(rows, list) and bool(rows) and isinstance(rows[0], dict) and "points" in fixture
            and isinstance(rows[0].get("providers"), dict))


def existing_binding(path, fixture, row, runs):
    """Per point of an existing provider reference: binding, or superseded by
    the row's campaign run that re-evaluates the same point and mu_R
    (``points`` generator 'fixture' of this path) in MadLoop's
    quadruple-precision stage with an ok reference record."""
    out = [{"binding": True} for _ in fixture["rows"]]
    for run_id in row["runs"]:
        run = runs[run_id]
        if run["points"].get("generator") != "fixture" or run["points"].get("fixture") != path:
            continue
        target = fixture_path(run_id)
        if not target.exists():
            continue
        rerun = json.loads(target.read_text())
        for index in range(len(fixture["rows"])):
            if not same_points((fixture["points"][index], fixture["mu_r"][index]),
                               (rerun["points"][index], rerun["mu_r"][index])):
                raise SystemExit(f"{run_id}: point {index} is not {path}'s")
            record, code = rerun["rows"][index]["reference"], rerun["rows"][index].get("madloop_status")
            if record["status"] != "ok" or evaluation_precision(code) != "quadruple" or record.get("outlier"):
                continue
            old, new = primary_values(fixture, index), rerun["rows"][index]
            out[index] = {"binding": False,
                          "superseded_by": {"fixture": str(target.relative_to(FIXTURES)), "row": index},
                          "strict_relative_deviation": {k: strict(old[k], new[k]) for k in COEFFICIENTS}}
    return out


COEFFICIENTS = ("born", "finite", "single_pole", "double_pole")


def run_entry(root, run, fixture_path):
    entry = {"run": run["id"], "fixture": str(fixture_path.relative_to(FIXTURES)) if fixture_path.exists() else None,
             "process_key": run["process"], "note": run.get("note"),
             "reference_notes": run.get("reference_notes", {}),
             "excluded_providers": run.get("exclude_providers", {}),
             "second_providers": run.get("second_providers", []),
             "second_provider_trigger": run.get("second_provider_trigger")}
    if run.get("components"):
        entry["components"] = run["components"]  # rule 5 components per sector (madloop_components.py)
    if run.get("madloop_params"):
        entry["madloop_params"] = run["madloop_params"]  # this run's MadLoop parameters over the campaign's
    if run.get("binding") is False:
        entry["binding"] = False  # an oracle run of another card (e.g. a technical epsIR = 0 run): no rule 1 reference
    if not fixture_path.exists():
        entry["status"] = "pending"
        return entry
    fixture = json.loads(fixture_path.read_text())
    codes = return_codes(fixture)
    records = [row["reference"] for row in fixture["rows"]]
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
        "parameter_overrides": fixture.get("parameter_overrides", {}),
        "points": len(fixture["points"]),
        "mu_r": fixture["mu_r"],
        "point_family": fixture.get("point_construction", {}).get("family", "exact terminating decimals"),
        "madloop_qp_point": bool(fixture.get("point_construction", {}).get("madloop_qp_point")),
        "point_labels": fixture.get("point_construction", {}).get("point_labels"),
        "scale_variation": fixture.get("point_construction", {}).get("scale_variation"),
        "primary_provider": fixture["primary_provider"],
        "validated_providers": fixture["validated_providers"],
        "madloop_return_codes": codes,
        "madloop_evaluation": run.get("madloop_evaluation", {}).get("mode", "quadruple"),
        "evaluation_precision": [evaluation_precision(code) for code in codes],
        "binding_rows": [i for i, record in enumerate(records) if record["status"] == "ok"],
        "outliers": {str(i): record["outlier"] for i, record in enumerate(records) if record.get("outlier")},
        "provider_accuracy_per_sector": sector_accuracy(fixture),
        "second_provider_outcome": second_provider_outcome(fixture, run.get("second_providers", [])),
        "squared_split_orders": fixture.get("squared_split_orders"),
        "per_helicity": bool(fixture.get("per_helicity")),
        "subprocess": run.get("subprocess"),
    })
    # Records of the M-SM campaign's fixtures (absent from M-QCD's).
    entry.update({key: fixture[key] for key in RUN_RECORDS if key in fixture})
    return entry


RUN_RECORDS = ("corrections", "complex_mass_scheme", "scheme_conventions", "tagged_photon_legs",
               "madloop_r2_couplings", "export_parameters")


EXISTING_R2 = "existing_r2_couplings.json"
QCD_ONLY_R2 = "QCD-only reference: MadLoop inserts the complete QCD R2 set (M-QCD)"


def existing_r2_targets(row, path):
    """The MadLoop exports (paths below the reference root) giving an existing
    fixture's R2 name list, or the reason it has none: the row's
    existing_r2_exports, else runs/required/<name>/madloop-export of
    required/<name>.json for an EW process (no list for a QCD-only one)."""
    explicit = row.get("existing_r2_exports", {})
    if path in explicit:
        return explicit[path]
    name = Path(path).stem
    if not path.startswith("required/"):
        raise SystemExit(f"{row['row']}: no R2 export known for {path} (set existing_r2_exports)")
    spec = required_spec.load_process(required_spec.DEFAULT_SPEC, name)
    if "EW" not in spec["corrections"]:
        return QCD_ONLY_R2
    return [f"runs/required/{name}/madloop-export"]


def command_existing_r2(args, data, runs):
    """Write the R2 name lists of the MadLoop exports behind the rows' existing
    fixtures (references.madloop_r2_couplings, from each export's
    ct_couplings.json) to <fixtures>/existing_r2_couplings.json."""
    import references

    root = reference_root(args)
    exports, without = {}, {}
    for row in data["rows"]:
        for path in row["existing_fixtures"]:
            targets = existing_r2_targets(row, path)
            if isinstance(targets, str):
                without[path] = targets
                continue
            for export in targets:
                key = Path(export).parent.name
                if key in exports:
                    if path not in exports[key]["fixtures"]:
                        exports[key]["fixtures"].append(path)
                    continue
                model = required_spec.load_process(required_spec.DEFAULT_SPEC, key, {
                    "mg5": root / "sources/MG5_aMC_v3_7_0", "reference": root})["madloop"]["model"]
                exports[key] = {"fixture": path, "fixtures": [path], "export": f"${{LOOP_REFERENCE_ROOT}}/{export}",
                                "madloop_model": Path(model).name,
                                **references.madloop_r2_couplings(root / export, model)}
    content = {"description": "The UFO R2 couplings the MadLoop exports of the existing M-SM references insert "
                              "(written by mqcd_campaign.py --campaign msm_campaign.json existing-r2: "
                              "references.madloop_r2_couplings on each export's ct_couplings.json; called_as = the "
                              "merged name MG5's call passes; the input of the rule-1 R2 correction, m-sm/PLAN.md "
                              "§1.4). Keyed by process; fixture paths below tests/fixtures/loop; without_r2_list: "
                              "the existing fixtures with no list and why.",
               "exports": exports, "without_r2_list": without}
    target = FIXTURES / LAYOUT["fixtures"] / EXISTING_R2
    target.write_text(json.dumps(content, indent=1) + "\n")
    print(f"{target.relative_to(REPOSITORY)}: {len(exports)} exports, {len(without)} fixtures without a list")


def existing_entry(path, row, runs):
    item = {"fixture": path, "status": "committed" if (FIXTURES / path).exists() else "pending"}
    if LAYOUT.get("r2_couplings"):
        targets = existing_r2_targets(row, path)
        item["r2_couplings"] = targets if isinstance(targets, str) else [
            f"{LAYOUT['fixtures']}/{EXISTING_R2}#{Path(t).parent.name}" for t in targets]
    if item["status"] == "pending":
        return item
    fixture = json.loads((FIXTURES / path).read_text())
    if not is_provider_reference(fixture):
        item["kind"] = "control (no provider merge; see the fixture's scope)"
        return item
    binding = existing_binding(path, fixture, row, runs)
    codes = return_codes(fixture)
    item.update({"kind": "provider reference",
                 "primary_provider": fixture.get("primary_provider", "madloop"),
                 "providers": list(fixture["rows"][0]["providers"]),
                 "validated_providers": fixture.get("validated_providers"),
                 "points": len(fixture["points"]), "mu_r": fixture["mu_r"], "scheme": fixture.get("scheme"),
                 "madloop_return_codes": codes,
                 "evaluation_precision": [evaluation_precision(code) for code in codes],
                 "provider_accuracy_per_sector": sector_accuracy(fixture, binding),
                 "point_binding": binding})
    return item


def command_manifest(args, data, runs):
    root = reference_root(args)
    rows = []
    for row in data["rows"]:
        route = data["restriction_codes"][row["restriction_code"]]
        entry = {**{k: row[k] for k in ("row", "class", "process", "restriction_code", "reference_kind", "tier",
                                        "extras")},
                 "pyamplicol_route": route, "note": row.get("note")}
        entry["references"] = [run_entry(root, runs[r], fixture_path(r)) for r in row["runs"]]
        entry["existing_references"] = [existing_entry(path, row, runs) for path in row["existing_fixtures"]]
        binding = []
        for ref in entry["existing_references"] + entry["references"]:
            if ref["status"] != "committed" or ref.get("binding") is False:
                continue
            if "point_binding" in ref:
                chosen = [i for i, b in enumerate(ref["point_binding"]) if b["binding"]]
            elif "binding_rows" in ref:
                chosen = ref["binding_rows"]
            else:
                binding.append({"fixture": ref["fixture"], "rows": None})  # a control fixture
                continue
            if chosen:
                binding.append({"fixture": ref["fixture"], "rows": chosen})
        entry["binding_references"] = binding
        if row.get("helicity_reference"):
            entry["helicity_reference"] = f"{LAYOUT['fixtures']}/{row['helicity_reference']}.json"
        if row.get("primary_provider"):
            entry["primary_provider"] = row["primary_provider"]
        if row.get("components"):
            entry["components"] = row["components"]  # the row's rule 5 components (madloop_components.py)
        rows.append(entry)
    manifest = {
        "schema": LAYOUT["schema"],
        "description": f"Reference manifest of the {LAYOUT['name']} campaign ({LAYOUT['plan']} §4.2), written by "
                       f"tools/loop_reference/mqcd_campaign.py manifest from {CAMPAIGN.name} and the committed "
                       "fixtures. Per row: process, pyAmpliCol route (restriction, fixed parameters), reference "
                       "runs (fixture path below tests/fixtures/loop, orders, points, MadLoop return codes, "
                       "evaluation precision and accuracy per point and loop squared split order, rule 1 outliers), "
                       "existing references (per point binding or superseded) and binding_references: the one "
                       "binding reference of every point. 'pending' marks a reference not committed yet. Parameters, "
                       "per-point reference records and per-helicity rows are the fixtures' own (the pyAmpliCol "
                       "request uses the fixture's parameters and fixed_parameters, the MadLoop card values).",
        "conventions": {
            "laurent": "MadLoop/BLHA C_eps = (4 pi)^eps / Gamma(1 - eps); physical couplings; initial spin/colour "
                       "average and final identical-particle factor included",
            "squared_split_orders": "QCD^2, QED^2 = summed g_s and e powers of the interfering amplitudes; a loop "
                                    "sector's born_sector is its orders minus the correction step",
            "binding_references": "per row, the fixtures and rows (0-based) that are the row's rule 1 reference: "
                                  "every ok row of the campaign runs, and the rows of an existing reference that no "
                                  "campaign run re-evaluates ('rows' None: an existing control fixture, not a "
                                  "provider merge, whose own format names its points). An existing reference's point_binding names, per point, "
                                  "the run row superseding it (the same exact point and mu_R, MadLoop's "
                                  "quadruple-precision stage, an ok record) with the strict relative deviation "
                                  "|a - b| / max(|a|, |b|) of its values from the superseding ones; a superseded "
                                  "point is no reference (its accuracy is not listed), while its other providers' "
                                  "values stay the second-provider values of rule 1 (ii) at that point",
            "evaluation_precision": "MadLoop's arithmetic per point from its return code 100 H + 10 T + U: H = 1, 2 "
                                    "double, 3 quadruple, 4 quadruple whose stability test failed (only at points "
                                    "with status 'none' or a declared outlier); None where the fixture keeps no code",
            "madloop_accuracy": "MadLoop's own ACC(i) of SLOOPMATRIX_THRES per point and loop squared split "
                                "order: ONE number over the three Laurent coefficients (madloop_settings."
                                "madloop_accuracy_definition), not a per-coefficient relative accuracy. At "
                                "double-precision points it is the binary64 estimate, which does not bound a "
                                "cancelling coefficient (required/uux_uux.json point 1: 0.0 with a single pole "
                                "1.2e-12 off the quadruple-precision value). In the quadruple-precision evaluation "
                                "0.0 means its two quadruple-precision evaluations (propagators in original and "
                                "reversed order) printed identical binary64 values for all three coefficients; that "
                                "test does not see an error both share: against mq-validate's double-double values "
                                "MadLoop quadruple-precision points with accuracy 0.0 differ by up to ~3.6e-13 "
                                "(e.g. E01 point 1, B03 point 1 with Ninja 3.4e-13) and by 3.5e-12 or more at the "
                                "g g > u u~ u u~ outliers, so an accuracy of 0.0 never satisfies rule 1 (i) and "
                                "every rule 1 failure at such a point is an outlier needing a ruling",
            "outliers": "per reference run, the rule 1 reference outliers (m-qcd/PLAN.md §1.4: the manifest names "
                        "every one), keyed by 0-based row: the fixture's reference.outlier record (rule, ruling, "
                        "the state of conditions i and ii, provider evidence)",
            "second_provider_outcome": "per triggered second provider and point: the strict relative difference "
                                       "|a - b| / max(|a|, |b|) of each coefficient from MadLoop's (the outcome of the "
                                       "§4.1 trigger named in second_provider_trigger)",
            "helicity_reference": "the fixture holding the row's per-helicity rows (per_helicity, with a reference "
                                  "record per entry: 'absolute' against the point's summed |Born| only for a "
                                  "vanishing helicity, else 'relative'; status 'none' with a reason where an entry is "
                                  "not a reference)",
            "per_helicity": "MadLoop SLOOPMATRIXHEL_THRES: colour average and identical-particle factor, no "
                            "helicity average; HelConfigs.dat helicity labels",
            "indexing": "rows, points, mu_r, point_labels, binding rows, point_binding, evaluation_precision, "
                        "provider_accuracy_per_sector and madloop_return_codes are aligned lists (row i = point i, "
                        "0-based); reference_notes, outliers and point_status keys are 0-based row indices; "
                        "scale_variation's point and copy_of_point are 1-based point numbers (mqcd_campaign.py run "
                        "--point), its row and copy_of_row the 0-based rows",
            "point_reference": {
                "where": "each fixture row's 'reference' record (rows[i].reference)",
                "status": "'ok': the row is a reference; 'none': no usable provider reference at this point "
                          "(reason given), validate it by internal oracles only",
                "outlier": "None, or a declared rule 1 reference outlier of an ok row (rule, ruling, conditions, "
                           "providers)",
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
                                                      "binary64 rounding (<= 1.1e-13 over the campaign): a larger "
                                                      "mismatch is a loop defect of the reference, not point "
                                                      "sensitivity (C01 point 1 of batch 2: 4.8e-13 from MadLoop's "
                                                      "helicity filter, Recola's own relation holding to 1e-15); at "
                                                      "madloop_qp_point points (S1-S3) it is the binary64 condition "
                                                      "of the limit point, bounded by the family's stated bound",
                "max_sector_double_pole_relative_error": "largest violation of the universal double pole over the "
                                                         "loop squared split orders (MadLoop's printed values, "
                                                         "relative to the point's largest double pole; "
                                                         "references.sector_pole_error); the merge refuses ok points "
                                                         "above its tolerance, the integrity tests recompute it from "
                                                         "the sector values and refuse ok regular points above "
                                                         "max(10 x MadLoop's largest sector accuracy, 2e-13) unless "
                                                         "the point is a declared outlier. At madloop_qp_point "
                                                         "points the reference Born is the double pole over the "
                                                         "factor, so the relation holds there by construction for "
                                                         "every sector with a Born partner; "
                                                         "born_double_pole_relative_mismatch is the falsifiable "
                                                         "quantity",
            },
            "fixture_tolerance": tolerance_scope(),
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
        flags.append(f"fixture={'yes' if fixture_path(run['id']).exists() else 'no'}")
        print(run["id"], " ".join(flags))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference-root", type=Path)
    parser.add_argument("--campaign", type=Path, help="campaign JSON (default: mqcd_campaign.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "points", "run", "combine", "merge", "fixture", "status", "relocate"):
        p = sub.add_parser(name)
        p.add_argument("runs", nargs="+", help="run ids ('all': every run); for relocate: fixture paths below "
                                               "tests/fixtures/loop")
    sub.add_parser("manifest")
    sub.add_parser("existing-r2", help="R2 name lists of the existing fixtures' exports (r2_couplings layouts)")
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
    data, runs = load(args.campaign)
    if args.command in ("manifest", "existing-r2"):
        args.runs = []
    {"export": command_export, "points": command_points, "run": command_run, "combine": command_combine,
     "merge": command_merge, "fixture": command_fixture, "manifest": command_manifest,
     "status": command_status, "relocate": command_relocate,
     "existing-r2": command_existing_r2}[args.command](args, data, runs)


if __name__ == "__main__":
    main()
