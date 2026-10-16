# RF front ends

Applies to each antenna port, match, balun, filter, switch, amplifier, pad and DC block.
Use the full tuning range, every gain state, both directions where applicable, and the fitted variant.
Record the source, number and reason for every limit before computing a verdict. Use the board
requirement or the part datasheet. If neither gives a limit, mark the chosen limit JUDGMENT and
explain its engineering basis. Without a limit, report INFO or UNKNOWN and name the missing requirement.
Missing data follows the not-published rule in workflow/40_checks.md.

Fetch manufacturer models into the review folder at review time. Do not collect or commit them
with this skill. For RF passives, baluns, filters and switches, request Touchstone files for the
exact part, package and switch state. For amplifiers, request files at the fitted voltage and
current, including frequencies below the intended band. Record frequency span, reference
impedance, temperature, bias, port order, reference plane and included matching parts. Confirm
whether the file includes the evaluation board before adding external networks. Different bias
points need different applicable files. [QORVO-FORUM, staff answers, 2026-02, unpaginated;
ADI-FORUM, threads 14881 and 103987, date and page UNSURE, search excerpts only.]

Treat Murata and TDK passive data as typical at the stated temperature and without DC bias unless
the particular file says otherwise. Coilcraft fitted models may cover only the first resonance;
de-embedded SRF can differ from mounted SRF. Record these limits rather than extrapolating a
pass. [MURATA-S, updated 2026-09-08, unpaginated; TDK-README, 2016-07-15, page UNSURE;
CC1721, Doc 1721, 2023-01-03, page UNSURE.]

For switch control edge checks, fetch the driver IBIS file and its package and voltage corner
when available. IBIS contains I/V, V/T and package data; it does not establish RF isolation or
phase noise. For bias and sequencing transients, fetch applicable vendor SPICE models and compare
their behavior with datasheet curves. Macromodel coverage is limited. Record unsupported behavior
and simulator compatibility. If any model is unavailable, record the requested file, source,
missing conditions, affected checks and the bench measurement or vendor question that settles
them. [IBIS-8.0, ratified 2025-12-05, sections 6.1 and 10.6; MT-099, Rev 0, 2009-01, p.1 to 2.]

Calculator names below without a package prefix are integration targets supplied separately.
Plot loss, impedance and stability across frequency whenever the curve determines the conclusion.

## RF-1 Matching networks and tolerance sensitivity
- Check: each matching L and C against value, tolerance, Q and SRF at the band. Sweep fitted
  tolerances and the source and load impedance corners. Check space for antenna and device
  tuning networks. [CC671, Doc 671-C, 2021-01-07, p.1 to 2 and Table 1; SWRA730, 2022-02,
  section 1.2 p.5 and section 4 p.14.]
- Why: nominal reactance alone misses component loss and resonance. Coilcraft compares Q of
  about 31 and 78 at 900 MHz for similar 2.7 nH 0402 inductors. [CC671, 2021-01-07, Table 1 p.1 to 2.]
- Compute: `rf.element_impedance`, `rf.match_sweep`; use applicable passive S-parameters when
  lumped models do not cover the band. Show return loss (RL) at the worst frequency and corner.
- Pass: RL and insertion loss (IL) meet the board allocation at every corner; Q and SRF meet
  the device or component guidance. Coilcraft's SRF guidance of ten times the operating frequency
  is a cited starting point, not a universal threshold. Any selected margin or tuning-footprint
  policy is JUDGMENT with its number and reason. [CC671, 2021-01-07, p.1 to 2.]
- Not published: fetch vendor S-parameters. If Q, SRF or tolerance response remains missing,
  mark UNKNOWN, preserve tuning options and require a VNA sweep. A vendor RL versus tolerance
  figure is UNSURE; settle it with the exact matching network model or measurement.

## RF-2 Balun type, ratio and full tuning range
- Check: identify the unbalanced port, differential impedance ratio and rated band against the
  chip's recommended impedance and the entire enabled tuning range. [MC-AN20-001, Rev B,
  2015-04-15, sheets 2 to 3; JTI-2450, 2019-01-18, p.1; JTI-1720, 2020-02-21, p.1.]
- Why: a wideband transceiver can have a narrowband fitted balun. ADI's AD9361/AD9364 board
  configuration uses a 2.4 to 2.5 GHz balun and calls for a change for other bands.
  [ADI-CFG, accessed 2026-10-15, Configuration Options, unpaginated.]
- Compute: digest band, ratio, loss and balance; `rf.mismatch` for the impedance ratio error.
  Use measured or vendor multiport response for loss and amplitude and phase balance.
- Pass: rated band covers every enabled tuning setting; impedance and balance meet the chip
  datasheet and board requirements. Any extra band-edge margin is JUDGMENT with its reason.
- Not published: missing chip impedance or balun balance stays UNKNOWN; ask the vendor and
  sweep the actual differential and single-ended ports on a VNA.

## RF-3 Balun DC paths and feed bypass
- Check: distinguish isolated windings, autotransformers, center taps and ceramic ground or
  DC-feed pins. Trace the chip's required DC bias, balun current and feed bypass.
  [MC-AN20-001, Rev B, 2015-04-15, sheet 2; JTI-1720, 2020-02-21, p.1 to 2.]
- Why: isolation and DC continuity differ by topology. The Johanson DC-feed connection requires
  its RF bypass network. [MC-AN20-001, Rev B, 2015-04-15, sheet 2; JTI-1720, 2020-02-21, p.1 to 2.]
- Compute: digest pin and winding tables; `rf.element_impedance` for the feed bypass across
  the band. Include bias current at all operating corners.
- Pass: DC paths, bypass and current satisfy both part datasheets. The 68 pF bypass on the
  1720BL is a part-specific example. A chosen extra current margin is JUDGMENT.
  [JTI-1720, 2020-02-21, p.1 to 2.]
- Not published: request the chip's RF-pin bias requirements and reserve a choke option.
  AD9361 TX center-tap bias details and the TCM1 Rev C 30 mA rating page are UNSURE here;
  confirm the exact datasheet revision and page before using either as evidence.

## RF-4 Filters over tuning, image and half-IF bands
- Check: at every tuning step and LO side, map the wanted band, image, half-IF response and LO
  leakage through each preselector and image filter. Include switched bands and control states.
  [AN150, 2014-08-04, p.11 to 12; M1838, 2003-03, p.2 to 3; MT-080, Rev 0, 2008-10, p.5 to 6.]
- Why: mixers respond at both LO plus IF and LO minus IF. Second-order mixer responses need
  their own rejection check. [AN150, 2014-08-04, p.11 to 12; M1838, 2003-03, p.2 to 3.]
- Compute: `spur.frequency_plan`; overlay every unwanted band on each filter's response.
  Use the filter's measured or vendor response for rejection, not frequency coincidence alone.
- Pass: wanted-band loss, image and half-IF rejection meet the receiver requirements at every
  setting; switched bands cover the required range without a gap. Any assumed interferer level
  or rejection limit is JUDGMENT with a number and reason.
- Not published: fetch filter S-parameters or perform a swept rejection measurement in each
  switch state. Missing rejection curves leave the corresponding check UNKNOWN.

## RF-5 LNA and PA bias and sequencing
- Check: bias choke impedance and SRF, DC blocks, bias resistor dissipation and current limit.
  For depletion-mode GaAs or GaN, trace hardware enforcement of gate bias before drain power
  and drain removal before gate-bias removal, including faults. [MC-149, Rev OR, 2025-09-08,
  p.2 to 4; CC945, 2017-10-04, p.1; CC671, 2021-01-07, p.2.]
- Why: choke behavior changes above resonance. Depletion-mode devices can draw uncontrolled
  drain current without the required gate bias. [CC945, 2017-10-04, p.1; MC-149, Rev OR,
  2025-09-08, p.2 to 4.]
- Compute: `rf.element_impedance` across the band; `calc.timing.budget` for sequence margins.
  Compare startup, shutdown and fault waveforms with the required order.
- Pass: bias, current and sequencing meet the amplifier datasheet. Set choke impedance and
  permitted RF leakage from the bias-tee requirement; any chosen impedance ratio is JUDGMENT
  with its number and reason. Sequencing relies on the fitted hardware for devices requiring it.
- Not published: request choke S-parameters and device sequencing limits. Sweep bias-tee S21
  and capture bias voltages during startup and faults. Missing limits stay UNKNOWN.

## RF-6 Amplifier stability including frequencies below the band
- Check: S-parameters over the entire available span, with fitted loading, bias choke and
  decoupling represented once. Check that the vendor stabilizing network is fitted.
  [AN154, 2000-11, p.19 to 22; MC-063, Rev B, 2015-04-14, sheets 1 to 2.]
- Why: the PGA-105+ needs its network for stability below 60 MHz. An in-band gain plot misses
  that risk. [MC-063, Rev B, 2015-04-14, sheets 1 to 2.]
- Compute: `rf.stability` with applicable `touchstone` data. Use
  `Delta = S11*S22 - S12*S21`, then K, absolute Delta, mu and reverse mu across frequency.
  The printed Delta in KS5072 is incorrect. [KS5072, 2012-03-22, p.3;
  AN154, 2000-11, p.19 to 22.]
- Pass: state the required stability criterion and pass its limits explicitly. For unconditional
  small-signal stability, the mathematical criterion is K greater than 1 and absolute Delta
  less than 1 throughout the checked span. Extra design margin is a requirement or JUDGMENT.
  A model at typical bias cannot establish a worst-case pass. [AN154, 2000-11, p.19 to 22.]
- Not published: no low-frequency S-parameters means UNKNOWN below the file. Reserve a series
  resistor or shunt RC option and measure stability over the available VNA span. Ground-via
  parasitics require layout evidence. [TR1108, Rev 1.0, 2012-07-17, p.5 and p.12 to 13.]
  The Edwards and Sinsky mu paper was not opened: UNSURE until verified. An open/short-port
  oscillation scan has no confirmed vendor procedure here; arrange a safe bench method first.

## RF-7 RF supply decoupling and mixed-value anti-resonance
- Check: each supply pin's capacitor SRF and first parallel resonance (PRF), mixed values,
  bias derating, and the feeding choke or bead. Include RF, IF and listed supply aggressors.
  [JTI-SRF, 1999-01-17, p.1; CY1032, Rev *C, 2014-11-03, p.2 to 3.]
- Why: capacitors become inductive above SRF. Parallel values can create a high-impedance
  peak. Cypress shows 22 nF with 100 pF performing worse than 22 nF alone over about 15 to
  175 MHz. [JTI-SRF, 1999-01-17, p.1; CY1032, Rev *C, 2014-11-03, p.2 to 3.]
- Compute: `rf.network_impedance`; plot the full network and each branch, including loss,
  mounting inductance and source impedance. Compare candidate damping networks.
- Pass: impedance peaks and resulting ripple stay within the supply-noise or RF leakage
  requirement at the band, IF and aggressors. If absent, select a numerical impedance or
  peaking limit as JUDGMENT and explain the ripple allocation that supports it.
- Not published: fetch biased capacitor data and applicable S-parameters. Assumed package
  ESL is UNSURE and cannot establish a pass; measure supply impedance or noise coupling.

## RF-8 RF switches, control domains and blocked-port discharge
- Check: driver VOH/VOL and abs max against switch VIH/VIL at supply corners, negative rails,
  supply order, default truth table, isolation and power at the highest frequency. Trace DC at
  every RF port and both sides of blocking caps. [PE42423, DOC-85742-4.02, 2026-07, p.1, 3, 10;
  AS179, rev 10/02A, p.2 to 3; AN27, DOC-02181-2, 2025-09, p.1 to 3.]
- Why: applicable GaAs parts need external DC blocks. SOI ports that would be at zero DC can
  acquire charge behind blocking caps without a discharge path. AN27 recommends 1 to 8 kohm
  shunts for its stated conditions. PE42423 isolation changes from 47 dB at 2.4 GHz to 43 dB
  at 6 GHz. [AS179, rev 10/02A, p.2 to 3; AN27, 2025-09, p.1 to 3;
  PE42423, DOC-85742-4.02, 2026-07, p.3.]
- Compute: digest control levels and sequence; `calc.divider.divider_output` for shifted levels;
  `rf.cascade` for path levels. Compare isolation against the maximum unwanted port power
  and permitted leakage. Verify DC discharge continuity in every state.
- Pass: levels, supply sequence, DC exposure, discharge path and power meet the exact switch
  datasheet or applicable app note. Isolation meets the board requirement across frequency.
  Any extra leakage margin or discharge-time target is numerical JUDGMENT with its reason.
- Not published: ask the vendor about discharge and permissible port DC. Preserve a shunt
  resistor option and measure transient port DC and isolation; missing data leaves UNKNOWN.

## RF-9 Antenna-port ESD capacitance, working voltage and assembly
- Check: protection capacitance at the RF band, RL, IL, working voltage against TX peak
  including mismatch, IEC rating, land pattern and paste instructions for tiny packages.
  TPD1E0B04 specifies capacitance at 1 MHz. [TPD1E0B04, SLVSDG9C, 2025-06, section 5.3 p.4;
  ESD101, Rev 1.4, 2017-10-27, p.1 and p.10.]
- Why: a shunt 1 pF at 5.8 GHz in 50 ohm gives about 3.43 dB RL and 2.62 dB IL
  (DERIVED, ideal shunt two-port, W26). RF voltage must be checked as peak, not RMS.
  [TPD1E0B04, SLVSDG9C, 2025-06, section 7.2.2 p.13 to 14.]
  At 200 mW, matched 50 ohm gives 3.16 V RMS and 4.47 V peak (DERIVED, W27). Compare
  4.47 V with the actual working range, not the RMS figure. Pluto Rev D RF ports were shorted
  by assembly under small ESD diodes; inspect paste and continuity. [TPD1E0B04, SLVSDG9C,
  2025-06, section 7.2.2 p.13 to 14; PLUTO-ESD, commit 0536458758, 2026-09-02,
  ESD Diode Issue, unpaginated.]
- Compute: `rf.shunt_c`, `rf.peak_voltage`; use a measured or vendor RF model for a real part.
  Include DC bias and maximum standing-wave voltage at the protection location.
- Pass: protection loss and mismatch meet their board allocations; peak plus DC stays inside
  the datasheet working range and the IEC rating meets the product requirement. Without a
  loss allocation, choose numerical limits as JUDGMENT and state the receiver or TX budget.
- Not published: fetch capacitance versus frequency or S-parameters; otherwise mark UNKNOWN
  and sweep a populated protection footprint. A shunt inductor as a qualified ESD replacement
  is UNSURE; confirm its surge behavior and the required protection test.

## RF-10 DC blocks and parallel resonance
- Check: capacitance at the lowest frequency, SRF and PRF through the highest frequency,
  voltage rating and bias derating. Check mounting orientation and broadband applicability.
  [JTI-SRF, 1999-01-17, p.1; ATC, 001-927 Rev E, 2005-01, coupling and DC blocking,
  page UNSURE.]
- Why: series capacitance limits low-frequency transmission; PRF can cause an in-band notch.
  Series resonance itself is not an automatic rejection of a coupling capacitor.
  [JTI-SRF, 1999-01-17, p.1.]
- Compute: `rf.dc_block`; plot loss across the full range. Include ESR and ESL and use measured
  response for PRF; a single series RLC model cannot establish its absence (DERIVED model limit).
- Pass: worst-case IL and voltage meet the board allocation and capacitor datasheet. No notch
  violates the required response. Any selected IL limit or voltage margin is JUDGMENT with its
  number and reason; an SRF crossing alone does not settle the loss budget.
- Not published: missing PRF needs vendor S-parameters or a VNA sweep in the mounted geometry.
  The plan's flat-mounted ATC 100A 100 pF notch near 1.6 GHz is UNSURE at page level;
  verify the ATC Rev E example page before treating that number as evidence.

## RF-11 Shield cans and cavity modes
- Check: frame land pattern, internal height against fitted parts, lid access for tuning and
  cavity modes against the band and strong harmonics. [ICM, Cavity Resonances of Shielding
  Boxes and Cans, 2023-08-01, unpaginated.]
- Why: a shielding cavity can resonate. An ideal 30 by 20 mm cavity with small height has a
  first mode near 9.01 GHz (DERIVED rectangular cavity, W31). [ICM, 2023-08-01, unpaginated.]
- Compute: `rf.cavity_modes` using internal dimensions and applicable dielectric assumptions.
  Record the highest significant RF or harmonic frequency and assess openings and loading.
- Pass: mechanical dimensions meet the frame datasheet. Modes meet the board's exclusion
  margin or a validated damping requirement. If absent, state a numerical frequency separation
  as JUDGMENT with its reason. An absorber plan alone does not establish a pass.
- Not published: frame guidance and loaded-cavity response are UNSURE until the exact frame
  datasheet and measurement are available. Require mechanical inspection and a swept coupling
  test. Via-fence spacing belongs to layout and stackup review; no fixed spacing is asserted here.

## RF-12 Attenuator pads and resistor power
- Check: pi or T topology, fitted resistor values and tolerances, rounding, attenuation, RL,
  dissipation in each resistor and its frequency response and derated rating. [VSH, Doc 60107,
  2009-02-04, p.2 and p.4; pad equations DERIVED from resistor network analysis.]
- Why: resistor parasitics affect high-frequency response. Power is unequal among pad parts.
  [VSH, Doc 60107, 2009-02-04, p.2 and p.4; dissipation DERIVED from network analysis, W29.]
- Compute: `rf.pad` with fitted values and maximum incident power. With K = 10^(A/20), an
  equal-impedance pi has shunts Z0*(K+1)/(K-1) and series Z0*(K*K-1)/(2*K). A T has each
  series Z0*(K-1)/(K+1) and shunt 2*K*Z0/(K*K-1). Include tolerances and reverse drive.
  [DERIVED; FRICKEY, 1994-02, p.205 to 206, Table I for ABCD conversion.]
  An ideal 6 dB pi pad in 50 ohm uses about 150.5 ohm shunts and 37.35 ohm series.
  At 1 W input, the input shunt, series and output shunt dissipate about 0.332 W, 0.333 W and
  0.083 W; about 0.251 W reaches the load (DERIVED, W29).
- Pass: fitted attenuation and RL meet the board allocation; each resistor meets its datasheet
  derating over temperature. Any extra power margin, package selection rule or attenuation
  error limit is numerical JUDGMENT with its reason.
- Not published: RF resistor data missing means UNKNOWN at high frequency. Fetch the exact
  package response or sweep the fitted pad; resistor technology alone does not prove the budget.

## RF-13 Lineup gain, noise, linearity and levels
- Check: gain, NF, IIP3, P1dB and each stage's input and output power for every path and gain
  state, including input blockers and the ADC full scale. [AN57-1, 5952-8255E, 2010-08-05,
  equation 2-3 p.8; MC009, Rev A, 2015-04-14, p.6.]
- Why: loss ahead of an LNA degrades noise figure; preceding gain weights later-stage
  intermodulation. [AN57-1, 2010-08-05, equation 2-3 p.8; MC-LIN, 2022-09-30,
  Cascaded P1dB and IP3, unpaginated; MC-5G, 2022-12-08, unpaginated.]
- Compute: `rf.cascade`; use passive loss at the operating temperature, applicable amplifier
  bias and measured data where needed. Tabulate levels and headroom stage by stage. Treat
  cascaded compression as an estimate and compare with a nonlinear model or measurement.
  [MC-LIN, 2022-09-30, unpaginated; MC-5G, 2022-12-08, unpaginated.]
- Pass: gain, NF, linearity and full-scale headroom meet the intake requirements; every stage
  stays within its datasheet input limit. Missing system targets need numerical JUDGMENT with
  their reason before a verdict; missing stage data does not become a favorable assumption.
- Not published: missing NF or IP3 leaves that budget UNKNOWN. Require Y-factor NF and two-tone
  testing at the relevant gain states. [AN57-1, 2010-08-05, p.12 to 13;
  AN150, 2014-08-04, p.56 to 57.]

## RF-14 RF substitutions and end-of-life changes
- Check: every alternate and replacement on RF nets against original capacitance, Q, SRF,
  band, pinout, DC path and applicable models. Rerun affected path budgets for each variant.
  [LIME-MINI2, docs/v2.2/index.rst, commit 72795ccf52, 2024-12-02, unpaginated.]
- Why: an end-of-life swap can change RF behavior despite compatible assembly. LimeSDR Mini
  2.x replaced a 1.2 pF shunt part with an 11 pF part and changed loopback attenuation.
  [LIME-MINI2, docs v2.2, commit 72795ccf52, 2024-12-02, unpaginated.]
- Compute: `rf.shunt_c`, `rf.element_impedance`, `rf.match_sweep` or `rf.cascade` for both
  fitted versions, using applicable frequency data and bias. Compare full curves and corners.
- Pass: absolute response and the change in RL, IL and loopback level stay inside the board's
  allocation; ratings and bias meet the replacement datasheet. Any chosen change budget is
  numerical JUDGMENT with its reason. Matching nominal value or footprint alone is insufficient.
- Not published: absent replacement RF data leaves UNKNOWN. Fetch the exact part's models
  at review time and measure the populated alternate over the full tuning range.
