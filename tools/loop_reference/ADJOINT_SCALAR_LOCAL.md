# Adjoint-scalar local counterterm controls

The source is the FeynRules NLO catalogue's `sgluons_NLO` version 1.0
(FeynRules 2.1.78, 17 October 2014), converted with MadGraph 3.7.0's existing
Python-2-to-3 importer. The original archive and all physics declarations remain
unchanged. This is a local tensor control, not a validated BSM process.

`adjoint_scalar_oracle.py` compares the source SS1, SS2, VSS1 and VVSS1 Lorentz
tensors with independently generated local ALOHA routines. The inputs contain
conserved complex off-shell momenta, a complete vector-component basis and
nonunit complex scalar/vector currents. The common ALOHA vertex phase
`-i * coupling` is removed explicitly. The largest scaled difference was
`2.54e-16`; the reference arithmetic is binary64, whereas the native tensor
contractions use exact dependency operations.

The existing MadGraph colour oracle separately checks adjoint Identity and
`f` (nine exact overlaps each), and the actual 22 ggSS R2 source entries with
11 distinct colour tensors (169 exact overlaps). Complex trace probes detect
the relative orientation of the mixed `d*f` tensors. The existing four-gluon
control supplies the shared four-adjoint colour basis used by the catalogue;
the scalar/vector Lorentz factor is checked separately. The recorded result is
`adjoint_scalar_local.json`.

```sh
python tools/loop_reference/adjoint_scalar_oracle.py \
  --ufo /path/to/converted/sgluons_NLO \
  --madgraph /path/to/MG5_aMC_v3_7_0 \
  --build-dir /path/to/workspace/adjoint-scalar-local \
  --output /path/to/workspace/adjoint-scalar-local.json
```

The production catalogue uses exact ordered spin/colour representations and
source expressions. It retains the actual source key, coupling, Laurent terms,
helper diagnostics and loop alternatives. Identical UV and R2 tensors share
this local certificate; no scalar coefficient or UV prescription follows from
it. The actual source request has 17 scalar CT rules and 63 basis entries, all
covered by the new SS/VSS/VVSS local branches. These counts are observations.
The scope selects `NP=QED=0` through exact coupling orders; the five-point
effective interactions remain in the source and are explicitly excluded from
this request, rather than removed by an arity limit.

Pending physical gates are scalar-coefficient/sign and loop-group comparison
with the original UFO and MadLoop importer, on-shell mass/field conventions,
heavy-flavour decoupling and complete amplitude normalization. The source has
no explicit particle field counterterms; its scalar two-point UV momentum
coefficient cancels exactly and its mass coefficient is nonzero. A physical
comparison must use those source declarations, not invent an extra LSZ factor.
NLOCT's stated HV construction is convention evidence, not certification of
these model coefficients. No full process, formal-Nc continuation or direct
R2 capability is claimed.

Preparing this actual source also needs the upstream Goldstone-alias fix
in [ufo_model_loader PR 3](https://github.com/alphal00p/ufo_model_loader/pull/3).
The tests used that isolated candidate without replacing the installed loader;
the normal consumer dependency remains a separate adoption gate.
