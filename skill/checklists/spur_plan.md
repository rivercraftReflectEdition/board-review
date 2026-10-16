# Spur plan

Run once per board, across the power tree, clocks, RF paths and converters. Record every tuning
setting, LO side, sample rate, operating mode and wanted band from intake. Missing data follows
the not-published rule in workflow/40_checks.md.

Use a board requirement or a part datasheet for each numerical limit. If neither gives one,
mark the limit JUDGMENT and record its number and engineering reason. Without a stated limit,
report INFO or UNKNOWN. A frequency overlap is a candidate for investigation; its amplitude
needs evidence [MT-003, ADI Rev A, 2008-10, p.2].

## SPUR-1 Aggressor list and switcher modes
- Check: list every periodic source by part, net, frequency range and mode. Include switchers,
  their PFM and forced PWM modes, clocks, dividers and active digital interfaces. Include
  startup, light load and spread limits from the part digests. PFM frequency varies with load
  [TPS62840, TI SLVSEC6D, 2020-03, sections 8.4.1 to 8.4.2; printed page UNSURE].
- Why: a fixed nominal switching frequency does not describe light-load PFM operation. Forced
  PWM gives a predictable frequency for RF interference planning, with an efficiency trade-off
  [TPS62840, TI SLVSEC6D, 2020-03, sections 8.4.1 to 8.4.2; printed page UNSURE].
- Compute: build the source table from the blocks and digests. Pass a named frequency or a
  pair of minimum and maximum frequencies per source to `calc.spur.search`. Select and record
  the harmonic order to cover the bands being reviewed.
- Pass: every operating mode has a source entry and a disposition against the board spur
  requirement. A choice of forced PWM or synchronization is a documented design decision,
  not an automatic pass. If chosen without a vendor requirement, mark it JUDGMENT and state
  why frequency predictability is needed.
- Not published: obtain min and max frequency and mode behavior from the vendor. Until then,
  mark the affected range UNKNOWN and scan the receiver or converter at minimum and maximum
  loads. The TPS62840 printed page is UNSURE; verify it in the review-time datasheet.

## SPUR-2 Harmonics and aliases
- Check: compare each aggressor harmonic with named RF, IF and baseband bands for every tuning
  and sampling setting. Include aliases after real sampling [MT-002, ADI Rev A, 2008-10, p.5].
- Why: sampling folds an out-of-band tone into the first Nyquist zone. A frequency match
  alone does not specify its level [MT-002, ADI Rev A, 2008-10, p.5; MT-003, ADI Rev A,
  2008-10, p.2].
- Compute: `calc.spur.search` with explicit order and sample rate; `calc.spur.alias` for a
  single tone. Inspect the harmonic markers and named band segments. The search returns
  indexed hit quantities with source, band, harmonic order, LO order and frequency bounds.
  With a source frequency range it checks the whole interval, including Nyquist folds.
  Optional source level bounds in dBFS must bound every destination product for that source;
  do not enter the fundamental's source amplitude as a bound on coupled products.
- Pass: no overlap within the stated search scope, or every overlap has a destination level
  below the board or converter datasheet spur limit. A reviewer-selected limit or order is
  JUDGMENT with its number and reason. Frequency screening alone remains INFO.
- Not published: missing harmonic levels leave the candidate UNKNOWN. Measure a terminated-input
  FFT or receiver spectrum across load and tuning states. Change the suspected switching
  frequency to identify its spur [AD51, ADI Analog Dialogue 51-04, 2017-04, p.2].

## SPUR-3 LO products, image and half-IF
- Check: search `abs(m f_LO +/- n f_aggressor)` in the named bands. Include odd LO harmonics
  for switching mixers and inspect image and half-IF responses at every filter state
  [MC011, Mini-Circuits AN-00-011 Rev B, 2015-04, p.1, 4; MT-080, ADI Rev 0, 2008-10,
  p.5 to 7; M1838, Maxim AN1838, 2003-03, p.2 to 3].
- Why: an aggressor can produce an IF response through mixing even when its own frequency
  misses the RF passband [M1838, Maxim AN1838, 2003-03, p.2 to 3].
- Compute: `calc.spur.search` with all LO settings and explicit aggressor and LO orders.
  Use `calc.spur.frequency_plan` at each RF setting with `lo_side` set to high or low.
  Compare the returned image and half-IF frequencies with measured or published rejection.
  The half-IF output is the response on the wanted RF side of the LO; use the search for
  the opposite side and other orders. At RF 100 MHz and IF 10.7 MHz, high-side LO is
  110.7 MHz, image is 121.4 MHz and half-IF is 105.35 MHz, from the mixer equations
  [M1838, Maxim AN1838, 2003-03, p.2 to 3; DERIVED].
- Pass: destination product levels and image and half-IF rejection meet the receiver requirement
  at every setting. Supply the required rejection explicitly. Any selected order bound or
  rejection limit without a requirement is JUDGMENT with its number and reason.
- Not published: missing mixer spur tables or filter rejection leave the relevant response
  UNKNOWN. Fetch filter S-parameters at the review-time bias and reference plane, record their
  conditions, and measure missing rejection. Do not treat the searched order as proof that
  higher products are absent [MC011, Mini-Circuits AN-00-011 Rev B, 2015-04, p.1, 4].

## SPUR-4 Supply ripple and modulation
- Check: ripple at every PLL, VCO, LO, oscillator, converter and reference supply, at the
  operating load and ripple frequency. Separate direct converter feedthrough from oscillator
  frequency modulation [AD45, ADI Analog Dialogue 45-09, 2011-09, p.1 to 3;
  PSMR, ADI Power Supply Modulation Ratio Demystified, 2018, p.1 to 2].
- Why: supply pushing produces VCO sidebands outside the loop bandwidth. A converter PSRR
  number describes direct supply coupling under its stated test conditions; it does not
  replace VCO pushing [AD45, ADI Analog Dialogue 45-09, 2011-09, p.1 to 3;
  MS-2210, ADI Designing Power Supplies for High Speed ADC, 2012-02, p.3].
- Compute: `jitter.ripple_sideband` for pushing outside the loop bandwidth;
  `calc.lc_tank.lc_filter` for supply filter peaking, with an explicit peak limit.
  Use `calc.spur.supply_spur` for converter feedthrough. Enter ripple and full scale as peak
  to peak voltage. Its PSRR argument is signed output-to-supply transfer: enter -60 dB
  for 60 dB rejection. A 10 mVpp ripple, 2 Vpp full scale and -60 dB transfer predict
  -106 dBFS [MS-2210, ADI, 2012-02, p.3; DERIVED].
- Pass: each calculated sideband or feedthrough spur is below its explicit board or datasheet
  limit at the relevant frequency and mode. If neither gives a limit, record a JUDGMENT
  number and its reason; do not add an unstated SFDR margin.
- Not published: missing pushing, PSRR or PSMR leaves the amplitude UNKNOWN. If a vendor SPICE
  model is available, fetch it at review time and record whether supply modulation is modeled
  at the required bias and frequency. Otherwise record model unavailable. Do not collect vendor
  models in the skill. Verify the assumed transfer by injecting known ripple and comparing
  the FFT or sidebands [MS-2210, ADI, 2012-02, p.3 to 4].

## SPUR-5 Sample clock spurs onto the signal
- Check: sample clock spur levels and the maximum analog input frequency, including
  undersampled inputs [AN-756, ADI Rev 0, 2004-12, p.5, equations 12 to 13].
- Why: a clock phase spur transfers to the sampled signal with a level shift of
  `20 log10(f_input / f_clock)` [AN-756, ADI Rev 0, 2004-12, p.5, equations 12 to 13].
- Compute: `jitter.spur_transfer` for each clock spur and input band. Pass the board's spur
  limit explicitly. Identify the output offsets with `calc.spur.alias` and the LO plan.
- Pass: every transferred spur is below the board or converter datasheet requirement. A
  reviewer-selected limit is JUDGMENT with its number and reason.
- Not published: clock spur levels missing at the required offsets leave the check UNKNOWN.
  Measure phase noise and discrete spurs at the converter clock pin under the actual supply
  and load conditions [MT-200, ADI Rev 0, 2012-01, p.4].

## SPUR-6 Spread spectrum and synchronization
- Check: document fixed frequency, PFM, forced PWM, synchronization and spread-spectrum settings
  for each regulator. Check the part's sync range and whether sync disables spread. TPS62913
  synchronization requires spread off [TPS62913, TI SLVSFP4B, p.18 to 19].
- Why: spread spectrum redistributes switching energy and can raise noise below about 100 kHz
  on sensitive signal-chain rails. Synchronization controls relative switching frequencies
  and avoids moving beat tones, but the chosen harmonics still need a spur check
  [OP1, ADI Optimizing Power Systems for the Signal Chain Part 1, 2021-03, p.3;
  OP2, Part 2, 2021-04, p.2; DOSTAL, ADI TA23725, 2022-03, unpaginated].
- Compute: `calc.spur.search` with each spread or mode range as the aggressor's lower and
  upper edges, and repeat for sync on and off. Record beat frequencies between switchers
  separately as aggressors; the calculator does not generate products between sources.
  Check settings against the exact regulator datasheet [LT8650S, ADI Rev D, p.10, 23;
  TPS62913, TI SLVSFP4B, p.18 to 19].
- Pass: each regulator has a mode plan whose destination spur levels and noise meet the
  board requirement. Any choice to prohibit spread on a sample clock, LO or DAC rail without
  a part-specific requirement is JUDGMENT; state the reason and the numerical noise or spur
  limit used. Vendor measurements must cover the actual rail, load and spread settings
  [OP1, ADI, 2021-03, p.3; OP2, ADI, 2021-04, p.2].
- Not published: missing noise spectra require a spread-on versus spread-off FFT or phase-noise
  comparison. Locking regulator sync to the system reference to place spurs at known offsets
  remains UNSURE; obtain a vendor analysis and measure the resulting spectrum. OP2's PDF file
  name and the TPS62913 publication date are UNSURE in the source inventory; verify the
  document identity at review time before relying on it.
