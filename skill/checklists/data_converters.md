# Data converters

Applies to every ADC, DAC and transceiver with on-chip converters. Apply each item to the
selected operating mode. Record why an ADC-only item does not apply to a DAC.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.
Every limit comes from the board requirement or the exact part's datasheet. If neither gives
one, record a numeric limit and the engineering reason as JUDGMENT. Without a limit, keep the
check INFO or UNKNOWN. A typical application circuit does not establish a guaranteed limit.

## ADC-1 Sample clock jitter against SNR
- Check: source phase noise, every buffer's additive jitter and converter aperture jitter at the
  highest analog input frequency, including an undersampled input. Record the integration band
  and whether noise sources are independent. [MT-008 Rev A, 2008-10, p.2, 4; AN-501 Rev A,
  2006-03, p.2; MT-200 Rev 0, 2012-01, p.3]
- Why: jitter SNR depends on analog input frequency. A clock suitable at baseband can lose SNR
  at IF. [MT-007 Rev A, 2008-10, p.3 to 4; AN-501 Rev A, 2006-03, p.2 eq.5 to 6]
- Compute: `calc.jitter.pn_to_jitter`, `calc.jitter.rss`, `calc.jitter.snr_jitter`. Record both jitter-only SNR
  and combined converter SNR. Choose integration bounds for the converter and clock noise
  bandwidth; the plan's cited guidance extends to at least the sample rate. [MT-008 Rev A,
  2008-10, p.2, 4; SBAA653A, rev 2025-04, p.2 to 3; MT-200 Rev 0, 2012-01, p.3]
- Pass: combined SNR and allowed loss meet the board requirement at the highest input
  frequency. If the requirement is missing, state a JUDGMENT loss budget and why the system
  can tolerate it. Do not infer an allowed loss from the converter's typical SNR.
- Not published: phase noise or aperture jitter missing means UNKNOWN. Measure clock phase
  noise and converter SNR at low and high input frequencies. [AN-835 Rev B, 2015-03, p.6 to 10;
  AN-501 Rev A, 2006-03, p.2 to 3]

## ADC-2 Clock path and input
- Check: trace the sample clock through every part. Compare coupling, input format, slew,
  amplitude, duty cycle and duty cycle stabilizer range with the converter datasheet. Check
  clock and output-driver supplies. Identify FPGA, CPLD or logic gates in the path. [AD9268
  Rev A, 2009-09, p.30 to 31; AD42, 2008-02, p.2 to 6; MT-031 Rev A, 2008-10, p.11]
- Why: logic in the sample clock path can add jitter; slow edges also worsen aperture
  uncertainty. [AD42, 2008-02, p.6; MT-200 Rev 0, 2012-01, p.3]
- Compute: `calc.jitter.snr_jitter` with each path element included. Digest slew, swing, duty and
  clock-frequency bounds for the selected mode. [AD9268 Rev A, 2009-09, p.30 to 31]
- Pass: clock input limits come from the converter datasheet and the SNR budget comes from
  the requirement. Any logic stage needs measured or specified added jitter inside that budget.
  If a slew budget must be chosen, state its numeric value and rationale as JUDGMENT.
- Not published: measure slew at the converter pins and measure the added jitter. Leave
  the affected clock budget UNKNOWN until bounded. [MT-200 Rev 0, 2012-01, p.3]

## ADC-3 Reference noise, capacitance and ESR
- Check: reference capacitor value at bias, ESR range, dielectric, placement and required
  series resistance. Check reference buffer transient drive for SAR conversion charge.
  [AD7980 Rev G, 2021-01, p.9, 18, 25; ADS8910B SBAS707B, 2018-01, p.6 to 7;
  AD9268 Rev A, 2009-09, p.41]
- Why: SAR conversion loads the reference dynamically. Low capacitor ESR can cause reference
  amplifier peaking; ceramic substitution needs a stability check. [SLYT339, AAJ 3Q 2009,
  p.14 to 15; SLYT355, AAJ 4Q 2009, p.7 to 9]
- Compute: `calc.mlcc_bias.mlcc_effective` with the capacitor vendor's bias curve. Compare
  reference noise and settling with the converter's reference budget. Fetch the reference or
  buffer SPICE model at review time if a transient or stability simulation is needed.
  [AD7980 Rev G, 2021-01, p.18; SLYT355, AAJ 4Q 2009, p.7 to 9]
- Pass: effective capacitance, ESR and series resistance meet the exact converter and reference
  datasheets at corners. Reference noise meets the requirement, or a stated JUDGMENT allocation
  with a numeric budget and reason.
- Not published: an example circuit is supporting evidence, not an ESR guarantee. Ask the
  vendor or measure reference settling and noise with the fitted capacitor. [SLYT339,
  AAJ 3Q 2009, p.14 to 15; SLYT355, AAJ 4Q 2009, p.7 to 9]

## ADC-4 SAR input RC and driver
- Check: external capacitance against sampling capacitance, kickback, available acquisition
  time, total drive resistance and driver settling, noise and distortion. Check the specified
  capacitor dielectric. [AD46, 2012-12, p.1 to 4; ADS8910B SBAS707B, 2018-01, p.57 to 58;
  AD7980 Rev G, 2021-01, p.17]
- Why: incomplete settling carries the previous sample into the next conversion. The driver
  must recover from charge redistribution. [AD46, 2012-12, p.1 to 4]
- Compute: `calc.converter.sar_rc`. Supply resolution, reference, acquisition time and filter
  capacitance. Include amplifier output resistance in the fitted resistance. Use the full-scale
  step for channel switching; use the optional sine kickback inputs only when that operating
  assumption applies. Fetch the driver SPICE model and ADC input model for a transient check.
  [AD46, 2012-12, p.1 to 4; ADS8910B SBAS707B, 2018-01, p.57 to 58]
- Pass: fitted resistance meets the calculated limit from required resolution and datasheet
  acquisition time. Pass any capacitance ratio as an explicit limit from the selected part's
  guidance. The published design guidance of external C at least 20 times sampling C and
  driver bandwidth at least four times RC bandwidth is a starting point, not a universal limit.
  State JUDGMENT and the reason if adopted without part-specific support. [AD46, 2012-12,
  p.1 to 4; ADS8910B SBAS707B, 2018-01, p.57 to 58]
- Not published: missing sampling capacitance or driver settling data means UNKNOWN for
  kickback. Ask the vendor and verify with a worst-case input step. [AD46, 2012-12, p.1 to 4]

## ADC-5 High-speed input drive and anti-alias filtering
- Check: series R, shunt C, balun or amplifier response over the actual analog band. Identify
  the Nyquist zone and all interfering bands that fold onto the wanted band. Use band-pass
  filtering for undersampled bands when lower and higher aliases need rejection. Check the
  transformer's low-frequency limit and input charge recovery. [AD9268 Rev A, 2009-09,
  p.26, 28; MT-002 Rev A, 2008-10, p.10; AN-742 Rev C, 2018-06, p.1, 3]
- Why: a low-pass filter can admit unwanted bands below an undersampled input. An input
  network suited to baseband can degrade IF SFDR. [MT-002 Rev A, 2008-10, p.10;
  AD9268 Rev A, 2009-09, p.26, 28]
- Compute: `calc.spur.alias` for band edges and blockers. Fetch balun and filter S-parameter files
  for the operating band and bias, and driver SPICE for settling when available. Compare
  measured or modeled rejection with the blocker budget. [MT-002 Rev A, 2008-10, p.5, 10;
  AN-742 Rev C, 2018-06, p.1, 3]
- Pass: filter rejection over every folding band meets the board dynamic-range and blocker
  requirements; driver noise and distortion meet their allocations. Missing requirements need
  explicit numeric JUDGMENT budgets with reasons, or the result remains INFO.
- Not published: record missing model coverage and sweep the fitted input network. Check
  SNR and SFDR at the band edges. [AN-835 Rev B, 2015-03, p.6 to 10]

## ADC-6 Common-mode ranges
- Check: VCM decoupling, driver VOCM or transformer center-tap connection, bias on AC-coupled
  inputs and common mode on DC-coupled inputs. Apply the selected part's common-mode servo
  rules. [AD9268 Rev A, 2009-09, p.26 to 27, 41; AD9361 Rev F, 2016-11, p.5, 17]
- Why: input bias and common-mode control depend on the converter. AC coupling alone does
  not establish the required bias. [AD9268 Rev A, 2009-09, p.26 to 27]
- Compute: `calc.divider.divider_output` for passive bias networks, including tolerance and
  leakage. Compare driver output range, differential swing and input common-mode range.
  [AD9268 Rev A, 2009-09, p.26 to 27; AD9361 Rev F, 2016-11, p.5, 17]
- Pass: common mode and both input pin excursions meet datasheet limits at corners. The
  datasheet, not a general VCM rule, supplies the limit.
- Not published: ask the vendor for input bias current and the allowed range. Measure
  common mode at the pins; an unbounded corner remains UNKNOWN.

## ADC-7 Parallel LVDS and CMOS interfaces
- Check: LVDS far-end or internal termination, CMOS load and series damping, I/O voltage,
  SDR or DDR capture timing, and SPI activity during capture. Include DAC input timing when
  relevant. [AN-586 Rev 0, 2002, p.1 to 3; MT-031 Rev A, 2008-10, p.8 to 9;
  AD9268 Rev A, 2009-09, p.32, 41]
- Why: output edge currents can couple into the analog input. Duplicate internal and external
  terminations change loading. [MT-031 Rev A, 2008-10, p.8 to 9; AN-586 Rev 0, 2002, p.1 to 3]
- Compute: `calc.timing.rc_edge` for a first load estimate. Fetch converter and receiver IBIS
  files at review time for edge, load and termination analysis. Derive the capture budget from
  the exact devices' timing tables. IBIS supplies I/V, V/T and package data; ordinary IBIS does
  not establish clock jitter. [IBIS-8.0, ratified 2025-12-05, section 6.1, section 10.6]
- Pass: termination and loading meet both endpoint datasheets. Series R is selected from the
  source and receiver limits or a stated JUDGMENT damping target with reason. Setup and hold
  meet the part-specific timing requirements. A generic 100 ohm LVDS termination is only a
  starting point. [AN-586 Rev 0, 2002, p.1 to 3]
- Not published: generic SDR and DDR timing guidance is UNSURE in the research. Read the
  exact converter and receiver timing sections; measure the capture eye if data is missing.

## ADC-8 JESD204 lanes
- Check: M, transport N', post-decimation sample rate, L and encoding for the selected mode.
  Check both endpoint lane ranges, differential termination, coupling caps and DC common mode
  when DC-coupled. [AD9680 Rev E, 2019-03, p.9, 68, 73; UG-1578 Rev 0, 2021-07, p.58, 184;
  ADC12DJ3200 SLVSD97A, 2020-04, p.5 to 6, 133]
- Why: transport bits and coding overhead set the physical lane rate. 8b/10b describes encoding,
  not the supported device rate or JESD revision. [SBAA402A, 2021-04, p.3 to 4]
- Compute: `calc.converter.jesd_lane_rate` with explicit bounds combined from both endpoints
  and the chosen standard. Calculate coupling impedance as `1/(2 pi f C)` at the frequency
  required by the endpoint guidance. [AD9680 Rev E, 2019-03, p.73; UG-1578 Rev 0, 2021-07,
  p.58, 184; JESD-SG, 2014-08, printed p.18]
- Pass: lane rate lies within the supported range at both ends and the selected JESD revision.
  Pass the smallest maximum and largest minimum explicitly. Coupling and termination limits
  come from the endpoint datasheets; an impedance target chosen without one is JUDGMENT,
  with its numeric value and rationale. [SBAA402A, 2021-04, p.3 to 4]
- Not published: obtain the endpoint mode tables and coupling guidance. Fetch applicable IBIS
  or IBIS-AMI models at review time; missing models need an eye or link-margin measurement.
  Record model coverage rather than substituting another part's model. [IBIS-8.0, ratified
  2025-12-05, section 6.1, section 10.6]

## ADC-9 SYSREF and synchronization
- Check: periodic, gapped or one-shot mode against coupling, receiver bias, clock relationship,
  setup and hold, SYNC wiring and multi-device skew. SYSREF must be an integer submultiple of
  the selected LMFC or LEMC. [SLYT628, AAJ 2Q 2015, p.15 to 17; UG-1578 Rev 0, 2021-07,
  p.27 to 28; AD9680 Rev E, 2019-03, p.11, 76, 80]
- Why: AC-coupled gapped or one-shot SYSREF can create a false restart edge. Continuous
  SYSREF can create spurs. Device exceptions exist, including ADC12DJ3200. [ADS54J54
  SLASE67A, 2019-08, p.28; ADC16DX370 SNVSA18C, 2014-08, p.54 to 55;
  ADC12DJ3200 SLVSD97A, 2020-04, p.10; SLYT628, AAJ 2Q 2015, p.16]
- Compute: `calc.converter.sysref` for frequency membership. For 204B use lane rate, F and K;
  for 64b/66b 204C use E from the mode table. Check coupling manually: `fc = 1/(2 pi R C)`
  uses the actual differential or single-ended bias network. Frequency membership does not
  establish setup and hold. [SLYT628, AAJ 2Q 2015, p.16 eq.1;
  UG-1578 Rev 0, 2021-07, p.27 to 28]
- Pass: integer division and allowed device dividers come from the interface mode. Use DC
  coupling for gapped or one-shot unless the part datasheet explicitly permits otherwise.
  For periodic AC coupling, use the receiver's duty and HPF guidance; the cited starting
  point is about 50% duty with corner below one quarter of SYSREF. If adopted without a
  part-specific bound, record this numeric limit and baseline-recovery rationale as JUDGMENT.
  Setup, hold and skew limits come from the endpoint datasheets. [SLYT628, AAJ 2Q 2015, p.16;
  LMK04828 SNAS605AS, 2020-05, p.21, 41; AD9680 Rev E, 2019-03, p.11, 76, 80]
- Not published: request missing setup and hold bounds. Repeat power cycles and resyncs to
  check latency and phase. This bench sequence is JUDGMENT; a vendor latency procedure is
  UNSURE and needs confirmation before claiming guaranteed deterministic latency.

## ADC-10 Supply ripple and noise
- Check: every rail's ripple spectrum against frequency-dependent PSRR or PSMR in the same
  operating mode. Include converter, transceiver synthesizer and LO rails. [MS-2210, 2012-02,
  p.3, 6; UG-570 Rev A, p.120 to 126; SLYT720, AAJ 2Q 2017, p.1 to 3]
- Why: ripple on analog rails can degrade EVM and create in-band products. Rejection depends
  on rail and frequency. [UG-570 Rev A, p.120 to 123; MS-2210, 2012-02, p.3]
- Compute: `calc.spur.supply_spur` with the documented rejection sign and amplitude convention;
  `calc.lc_tank.lc_filter` for rail filter resonances. Pass filter limits explicitly. Compare
  switcher harmonics with the receiver and converter spur plan. [MS-2210, 2012-02, p.3, 6;
  OP1, 2021-03, p.3 to 5; SLVAEW7, 2020-09, p.3]
- Pass: every predicted supply product meets the board SFDR, EVM and spur allocation with
  the required margin. If the requirement gives no margin, state a numeric JUDGMENT margin
  and its reason. A regulator or LDO choice alone does not establish the budget.
- Not published: missing PSRR or PSMR needs a rail injection test and FFT. Record rail,
  injection frequency, ripple amplitude and converter configuration. [AN-835 Rev B, 2015-03,
  p.27; MS-2210, 2012-02, p.3 to 4]

## ADC-11 Unused inputs, outputs and channels
- Check: unused analog and digital pins against the exact datasheet and enabled IP mode.
  Distinguish a disabled channel from an enabled but undriven one. [UG583 v1.29, 2025-12-23,
  section "Unused ADC & DAC Pins"; section page UNSURE]
- Why: permitted tie-offs can depend on whether a converter is enabled and AC-coupled.
  One unused-channel rule does not cover every mode. [UG583 v1.29, 2025-12-23,
  section "Unused ADC & DAC Pins"; section page UNSURE]
- Compute: none. Record pin-by-pin tie-offs and the actual hardware and firmware mode.
- Pass: tie-offs match the selected part's datasheet for that mode. If only general guidance
  exists, mark the proposed tie-off UNSURE and obtain part-specific confirmation.
- Not published: request vendor confirmation. The UG583 page number was not recorded in
  the research; verify the named section before using its examples as evidence.

Model records stay in the review folder. Fetch vendor models for the exact part, package and
mode at review time; do not collect or commit a model library. Record filename, source URL,
revision, date, bias, temperature, frequency coverage and reference plane. For S-parameters,
establish whether fixtures and matching parts are included. Verify model behavior against the
datasheet before using it outside the example conditions. Macromodels need not cover every
noise or nonlinear effect. [MT-099 Rev 0, 2009-01, p.1 to 2]
If a model is unavailable, record source_unavailable, the unanswered parameter and the vendor
question or measurement that would settle it. Do not replace missing evidence with an
uncited model. IBIS signal-integrity evidence cannot establish phase noise or aperture jitter.
[IBIS-8.0, ratified 2025-12-05, section 6.1, section 10.6]
