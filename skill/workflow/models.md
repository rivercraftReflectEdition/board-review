# Manufacturer models

Fetch models for the specific review. Keep the original files in the review folder, outside
the skill and this repository. Do not collect or commit manufacturer models. Record the URL,
download date, file name, SHA-256, model revision, ordered MPN and the checks that use each file.
This storage and provenance policy is a review rule.

## Fetch the right files

| Part kind | Files to request | Where to look |
|---|---|---|
| RF amplifier, switch, filter, balun or attenuator | Touchstone S-parameters at the board's bias and selected state. Include every port needed for the path and its terminations. | Manufacturer product page, design resources, simulation downloads or evaluation-board page; ask support for missing bias points. Bias and reference-plane examples: [QORVO-FORUM, staff replies, 2026-02; ADI-FORUM, threads 14881 and 103987, search excerpts only]. |
| Capacitor, inductor or ferrite bead | S-parameters for the exact value and package. Request the applicable DC voltage or current, temperature and mounting plane. For a biased MLCC, request a bias-dependent model or data for the operating voltage. | Manufacturer component search and model libraries, including Murata S-parameter pages, TDK model library and Coilcraft model downloads. [MURATA-S, updated 2026-09-08, web page; TDK-README, 2016-07-15, model conditions; CC1721, 2023-01-03]. |
| Clock or logic driver and receiver | IBIS file, selected component, package, pin and buffer model. Request the supply and process corners needed for the termination check. | Manufacturer product page under simulation or design resources; use the vendor's IBIS model selector. IBIS describes I/V, V/T, package and C_comp data. [IBIS-8.0, 2025-12-05, section 6.1]. |
| Regulator, PLL or amplifier requiring circuit simulation | Vendor SPICE subcircuit, dependencies, symbol or example circuit, simulator and version requirements. Record which behaviors the vendor claims it models. | Manufacturer product page, simulator component library or vendor design tool. Compare the model with the datasheet before using it as evidence. [MT-099, Rev 0, 2009-01, p.1 to 2; LTSPICE-HELP, 26.0.2, 2026-04-29, Model Compatibility]. |

These locations are search starting points. Availability for an individual MPN is UNSURE until
the reviewer retrieves and inspects the file. The plan does not give page numbers for TDK's
model conditions or CC1721. Their detailed operating conditions remain UNSURE until the reviewer
reads and cites the supplied readme or model documentation. A model's download location alone
does not establish its applicability.

## Decide whether the model applies

For each model, write an applicability record beside the original file. The digest may also
reference Touchstone files under `rf.touchstone`. Include the following evidence and any gap:

- Match the ordered part, package, silicon revision where relevant, operating state, supply,
  bias current or voltage, temperature and loading. Keep separate files for separate bias
  points. Qorvo's TQL9092 example uses distinct 3.3 V and 5 V files. [QORVO-FORUM, staff replies,
  2026-02, TQL9092 thread; no page numbering].
- Record whether the reference plane is at the component pins, fixture pads, connectors or
  evaluation board. Record de-embedding and any tuning or matching parts included. Do not
  count an included matching network again when cascading. The plan reports a de-embedded
  Qorvo TQP9111 model and ADI files that can include the evaluation board. The ADI claim is
  UNSURE because the plan has only search excerpts; settle it from the supplied model notes.
  [QORVO-FORUM, staff replies, 2026-02, TQP9111 thread; ADI-FORUM, threads 14881 and 103987].
- Match the required frequency range to the file range. Record the grid spacing around
  resonances and band edges. Interpolation can miss a narrow feature; refusing extrapolation
  is a review rule. [SHLEPNEV, 2010-02-04, slides 11 to 14].
- Record port order, physical pin map, reference resistance per port, single-ended or
  mixed-mode definition, parameter type and numeric format. Touchstone port order depends
  on port count and the two-port data-order keyword. [TS2.1, 2024-01-26, p.6 to 18].
- For inductors, establish whether the file is measured or fitted and which resonances it
  covers. The plan attributes a first-resonance limitation and a mounted versus de-embedded
  SRF difference to CC1721. This is UNSURE until the reviewer checks the model's documentation
  and cites its page. [CC1721, 2023-01-03].
- For SPICE, compare the DC operating point and relevant AC or transient response with the
  datasheet at the same conditions. Record omissions affecting the check. Macromodels need
  not include every nonlinearity or noise mechanism. [MT-099, Rev 0, 2009-01, p.1 to 2].
- For IBIS, record the selected model and corners. Do not use ordinary IBIS buffer tables as
  evidence of oscillator phase noise, clock jitter or PLL dynamics. Those are separate from
  buffer I/V and V/T data; IBIS-AMI jitter parameters concern SerDes models. [IBIS-8.0,
  2025-12-05, sections 6.1 and 10.6].

Run a passivity check on a model claimed to be passive. The mathematical boundary is a maximum
singular value of 1 at every frequency. This check does not establish causality or a correct
reference plane. A powered amplifier may have gain and is not expected to satisfy that passive
boundary. [SHLEPNEV, 2010-02-04, slides 6 to 14].

Use limits from the board requirement or datasheet. If neither gives a limit, state the number
and reason and mark the check JUDGMENT. No calculator supplies a pass threshold automatically.
A typical manufacturer file normally supports a nominal analysis. A successful nominal result
does not establish a pass across operating corners. This is the review's evidence policy.

## Record an unavailable model

If a required model cannot be obtained, write a `model_unavailable` record. An inaccessible file
does not show that the manufacturer publishes no model. Record what was tried, accept the user's
statement that a model is unavailable, and continue with the checks that have evidence. This
follows the distinction in [the datasheet workflow](20_datasheets.md).

For example, keep this as a separate review record under `models/` in the review folder:

```json
{
  "status": "model_unavailable",
  "mpn": "SYNTHETIC-RF-PART",
  "kind": "touchstone",
  "required_conditions": {
    "bias_v": 3.3,
    "bias_a": 0.02,
    "temperature_c": 85,
    "reference_plane": "component pins",
    "frequency_range_hz": [100000000, 3000000000]
  },
  "unavailable": {
    "reason": "The supplied file covers only a different bias point",
    "tried": ["Inspected the supplied model and its readme"],
    "checks": ["RF path return loss and stability"],
    "consequence": "These model-dependent checks remain unknown at the board's bias",
    "action": "Obtain the correct model or measure the assembled path with a VNA"
  }
}
```

The numbers above illustrate the record structure; they are not model data or limits. There is
schema support for this record in schemas/datasheet_digest.schema.json. Validate it with
`python -m boardreview validate FILE --schema digest`. A readable digest may instead include
these records in its optional `model_unavailable` list. Attach the record to the report and
keep affected conclusions unknown. A bounded datasheet calculation or bench measurement can settle
a check independently; state that evidence explicitly.

## Use the files

`sim.touchstone.read_touchstone` loads a local file into a `Network` with frequency in Hz,
complex S matrices and positive real per-port references. `sim.touchstone.parse_touchstone`
accepts text with a port count or source name. The reader handles Touchstone 1.x, 1 to 4 ports,
and 2.0/2.1 Full, Lower and Upper matrices. It handles RI, MA and DB data and converts S, Z, Y,
H and G parameters to S. Noise blocks are skipped with an explicit note. Mixed-mode keywords
and unsupported keywords are rejected. Format and normalization rules: [TS2.1, 2024-01-26,
p.4, 6 to 18, 24 to 29]. Keep the manufacturer's original file and applicability record.

`sim.touchstone.interpolate` returns a network on a supplied frequency grid. It interpolates
real and imaginary parts linearly and refuses frequencies outside the source file.
`sim.touchstone.renormalize` changes positive real reference resistances.
`sim.touchstone.cascade` connects port 2 of the first two-port to port 1 of the second. Supply
an explicit common grid if their grids differ. It matches the internal references before a
wave-chain cascade and retains the external port references. These are data transforms, not
pass/fail analyses. [FRICKEY, 1994-02, p.205 to 211, Tables I and VI; SHLEPNEV, 2010-02-04,
slides 11 to 14]. Complex reference impedances are outside this implementation's scope.

`sim.touchstone.return_loss`, `sim.touchstone.insertion_loss`, `sim.touchstone.vswr` and
`sim.touchstone.passivity` each return a `Result` with a summary, key numbers and a frequency
plot. Ports are numbered from 1. Other ports are terminated in their listed references. Limits
are optional arguments; without one the result is informational and asks for the missing limit.
VSWR is unknown when reflection exceeds unity, because passive VSWR is undefined there.
Use `context="worst_case"` only when the supplied model justifies it. Passivity takes
`max_singular_value=1` for the mathematical passive boundary. Any allowance for numerical error
must be supplied and recorded by the reviewer. Sampled results cover only the supplied grid.
[FRICKEY, 1994-02, p.205 to 206; SHLEPNEV, 2010-02-04, slides 6 to 14].

For a SPICE model, preserve its `.SUBCKT` pin order and `.lib` or `.include` dependencies in the
review's circuit. The existing `sim.setups.run_loop_gain`, `sim.setups.run_load_step`,
`sim.setups.run_startup` and `sim.setups.run_impedance` use that circuit or an explicitly
documented equivalent model. They do not import Touchstone or IBIS files. LTspice's `.NET`
exports two-port parameters during AC analysis; it is not a Touchstone importer. LTspice 26.0.2
also has no native IBIS importer. [LTSPICE-HELP, 26.0.2, 2026-04-29, .NET and Model Compatibility;
model capability table in the review plan].

Do not turn S-parameter samples into a transient model without a separate, validated fitting
step. Frequency-domain passivity alone does not validate a transient realization.
[SHLEPNEV, 2010-02-04, slides 6 to 14; GUSTAVSEN, 1999-07, p.1052 to 1061]. Treat unsupported
encrypted model formats as unavailable for the selected simulator. Simulator compatibility is
UNSURE until a local smoke test runs. Preserve the setup and sanity-check results with each run;
see [checks](40_checks.md). All fetching and model selection happens at review time. This
package only reads local model files.

## Source keys

| Key | Document and location |
|---|---|
| TS2.1 | IBIS Open Forum, Touchstone File Format Specification Version 2.1, ratified 2024-01-26, p.4, 6 to 18, 24 to 29. |
| FRICKEY | D. Frickey, Conversions Between S, Z, Y, h, ABCD, and T Parameters, IEEE T-MTT 42(2), 1994-02, p.205 to 211, Tables I and VI. Positive real references only here; see Marks and Williams, IEEE T-MTT 43(4), 1995-04, comments on Frickey. |
| SHLEPNEV | Y. Shlepnev, Quality metrics for S-parameter models, DesignCon IBIS Summit, 2010-02-04, slides 6 to 14. |
| GUSTAVSEN | Gustavsen and Semlyen, vector fitting, IEEE Trans. Power Delivery 14(3), 1999-07, p.1052 to 1061. |
| IBIS-8.0 | IBIS Version 8.0, ratified 2025-12-05, sections 6.1 and 10.6. |
| MURATA-S | Murata S-parameter data pages, updated 2026-09-08, web pages without page numbering. Check the retrieved file's conditions. |
| TDK-README | TDK Equivalent Circuit Model Library readme, 2016-07-15. Exact condition pages UNSURE in the plan. |
| CC1721 | Coilcraft Doc 1721, When to use S-parameters, 2023-01-03. Exact claim pages UNSURE in the plan. |
| QORVO-FORUM | Qorvo staff answers on TQP9111 and TQL9092 S-parameters, 2026-02, forum threads without page numbering. |
| ADI-FORUM | ADI EngineerZone threads 14881 and 103987 on S2P reference planes, search excerpts only; date and full context UNSURE. |
| LTSPICE-HELP | LTspice 26.0.2 installed help, 2026-04-29, .NET and Model Compatibility topics, no page numbering. |
| MT-099 | ADI MT-099, Analog Circuit Simulation, Rev 0, 2009-01, p.1 to 2. |
