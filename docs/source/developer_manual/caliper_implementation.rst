.. _developer-caliper-implementation:

Caliper Implementation
======================

Overview
--------

The Calipers feature is a temporary waveform measurement subsystem.

It provides:

- Draggable start and end markers.
- Mirrored marker lines across all waveform plots.
- Source-waveform selection.
- Automatic peak detection inside the selected interval.
- Temporary detected-peak graphics.
- Estimated heart rate or periodic cycle rate.
- Full-selected-range projection markers.
- Performance instrumentation using the existing ``[PERF]`` format.

Caliper state is separate from annotation state.

Caliper results are not written to annotation CSV files and do not affect waveform completion.

Primary Modules
---------------

``app.py``
   Creates the caliper controls, result display, timers, signal connections, and initial state.

``callbacks.py``
   Implements source selection, marker creation, synchronization, segment extraction, peak detection, rate calculation, projection rendering, cleanup, and timing wrappers.

Required Dependency
-------------------

Peak detection uses SciPy signal-processing functions.

The project requirements should include:

.. code-block:: text

   scipy

Functions currently used include:

- ``scipy.signal.butter``
- ``scipy.signal.detrend``
- ``scipy.signal.find_peaks``
- ``scipy.signal.sosfiltfilt``

If SciPy is unavailable, the app should leave annotation behavior functional and report that automatic peak detection is unavailable.

Time Coordinate Model
---------------------

Waveform X values are stored as high-resolution absolute epoch seconds.

Example:

.. code-block:: text

   1675398664.3804398

The plot axis displays relative seconds through ``RelativeAxis.tickStrings()``:

.. code-block:: python

   displayed_time = absolute_epoch_time - recording_start_time

This affects only the displayed tick labels.

Caliper marker positions, detected peak times, and projection positions remain in absolute epoch coordinates.

Durations are calculated through subtraction:

.. code-block:: text

   duration_seconds = end_epoch - start_epoch

Detected peak indices are mapped back to the original absolute time vector:

.. code-block:: text

   peak_time = selected_time_values[peak_index]

Projection positions are generated from an absolute anchor and an interval multiple. This avoids cumulative timing drift.

Configuration
-------------

A module-level configuration list defines which waveform names are eligible for caliper measurement.

Example configured signals may include:

- ``I``
- ``II``
- ``III``
- ``V``
- ``AVF``
- ``AVL``

Only configured signals with finite loaded data are added to the source dropdown.

Detector settings are stored by waveform name.

Typical settings include:

- Detector type.
- Rate display unit.
- Minimum expected rate.
- Maximum expected rate.

ECG signals use the ECG detector and display ``BPM``.

Generic periodic signals use the generic detector and may display ``cycles/min``.

Caliper State
-------------

Important state attributes include:

``calipers_enabled``
   Whether the feature is visible and active.

``caliper_adjust_enabled``
   Whether caliper markers can be dragged.

``caliper_projection_enabled``
   Whether projection graphics are currently shown.

``caliper_projection_requested``
   The user's requested projection state.

``caliper_source_plot_idx``
   Index of the waveform used for peak detection.

``caliper_start_time``
   Absolute epoch coordinate of the first marker.

``caliper_end_time``
   Absolute epoch coordinate of the second marker.

``caliper_detected_peak_times``
   Absolute epoch coordinates of accepted temporary peaks.

``caliper_detected_peak_values``
   Signal values corresponding to accepted peak locations.

``caliper_average_interval_sec``
   Mean accepted peak-to-peak interval.

``caliper_median_interval_sec``
   Median accepted peak-to-peak interval.

``caliper_estimated_rate``
   Calculated rate in BPM or cycles/min.

``caliper_measurement_status``
   Timing-consistency status.

``caliper_start_lines``
   Start-marker graphics across all plots.

``caliper_end_lines``
   End-marker graphics across all plots.

``caliper_peak_graphics``
   Temporary peak-dot graphics on the source plot.

``caliper_projection_graphics``
   Temporary projection lines across all plots.

UI Controls
-----------

The caliper toolbar contains:

``Calipers ON/OFF``
   Enables or disables the complete feature.

``Adjust ON/OFF``
   Enables marker dragging and suppresses normal annotation endpoint clicks.

``Source``
   Selects the waveform used for peak detection.

``Projection ON/OFF``
   Controls full-selected-range projection graphics.

``Reset``
   Repositions both markers around the center of the current visible X-range.

``Result label``
   Displays the source, peak count, calculated rate, and status.

Enabling Calipers
-----------------

When enabled:

1. The source waveform is read from the dropdown.
2. The current visible X-range is obtained.
3. Two initial positions are placed around the center of the view.
4. Marker graphics are created across all waveform plots.
5. Measurement calculation is triggered.

The initial separation is based on a configured fraction of the visible X-range, with a minimum separation safeguard.

Turning Calipers off:

- Removes all temporary graphics.
- Clears the current measurement.
- Disables Adjust and Projection.
- Does not change annotation state.

Adjust Mode
-----------

Adjust mode prevents conflict between draggable caliper lines and annotation plot clicks.

When Adjust mode is enabled:

- Caliper lines are movable.
- Annotation endpoint clicks are ignored.
- Mirrored lines remain synchronized.

When Adjust mode is disabled:

- Caliper lines remain visible.
- Lines are not movable.
- Annotation endpoint handling resumes.

The annotation click handler checks caliper-adjust state before processing an annotation click.

Marker Synchronization
----------------------

Each plot receives a start and end ``InfiniteLine``.

Moving a line updates:

- The corresponding absolute start or end time.
- Matching lines across every waveform plot.
- The temporary measurement display.
- Peak calculation after drag completion.
- Projection spacing and visible projection graphics.

A synchronization guard prevents recursive position-change signals while mirrored lines are updated.

Selected Segment Extraction
---------------------------

Peak detection operates only on samples between the two caliper positions.

Segment extraction:

1. Selects ``leads_ds[caliper_source_plot_idx]``.
2. Uses the corresponding entry in ``time_axes_by_lead`` when available.
3. Falls back to the global ``time_axis``.
4. Truncates mismatched time/signal arrays to their shared length.
5. Restricts samples to the caliper interval.
6. Removes non-finite samples.
7. Sorts by time.
8. Removes duplicate timestamps.
9. Returns the source name and detector settings.

The waveform file is not reread from Turbo. Calculation uses arrays already loaded in memory.

Sampling-Frequency Estimation
-----------------------------

Sampling frequency is estimated from the selected time vector:

.. code-block:: text

   median_dt = median(diff(time_values))
   sampling_frequency = 1 / median_dt

Only positive finite time differences are used.

If sampling frequency cannot be estimated, calculation returns an unable status.

ECG Peak-Detection Pipeline
---------------------------

The ECG detector uses a lightweight, polarity-independent QRS-energy method inspired by Pan–Tompkins-style processing.

Processing steps:

1. Linear detrending.
2. QRS-focused Butterworth bandpass filtering.
3. Signal differentiation.
4. Squaring of the derivative.
5. Moving-window energy integration.
6. Adaptive candidate peak detection.
7. Local refinement to the strongest absolute filtered deflection.
8. Minimum-spacing enforcement.

The detector works with both upright and inverted complexes because refinement uses absolute filtered amplitude.

ECG Filter Parameters
---------------------

Typical current parameters are:

.. code-block:: text

   Bandpass low cutoff:       5 Hz
   Bandpass high cutoff:      25 Hz
   Integration window:        0.08 seconds
   Refinement search radius:  ±0.08 seconds

Low Cutoff
~~~~~~~~~~

The low cutoff reduces:

- Baseline wander.
- Respiratory drift.
- Slow electrode movement.
- Low-frequency displacement artifact.

A lower value such as 3 Hz may preserve more energy from wide ventricular complexes.

High Cutoff
~~~~~~~~~~~

The high cutoff reduces:

- Muscle noise.
- High-frequency monitor noise.
- Sharp artifacts.
- Some pacing-spike energy.

The cutoff should be validated against representative peri-arrest signals.

Integration Window
~~~~~~~~~~~~~~~~~~

The squared derivative is smoothed with a moving average.

At 120 Hz, an 80 ms window contains approximately:

.. code-block:: text

   0.08 × 120 ≈ 10 samples

This groups nearby QRS slopes into one candidate energy region.

A longer 100–120 ms window may better combine very wide complexes but may reduce separation at high rates.

Refinement Window
~~~~~~~~~~~~~~~~~

Each integrated-energy candidate is refined to the strongest absolute filtered deflection within the configured radius.

At 120 Hz, a radius of 80 ms searches approximately:

.. code-block:: text

   ±10 samples

A window that is too large may snap to a neighboring pacing spike, T wave, or artifact.

Candidate Thresholds
--------------------

The integrated-energy height threshold is:

.. code-block:: text

   median energy + 0.35 × energy standard deviation

Candidate prominence is:

.. code-block:: text

   0.15 × energy standard deviation

These thresholds adapt to the selected segment rather than using a fixed waveform amplitude.

Minimum Peak Spacing
--------------------

Minimum peak spacing is derived from the configured maximum rate:

.. code-block:: text

   minimum spacing = 60 / maximum rate

For a maximum ECG rate of 300 BPM:

.. code-block:: text

   minimum spacing = 0.20 seconds

At 120 Hz:

.. code-block:: text

   minimum samples = 24

If two refined candidates violate minimum spacing, the candidate with the stronger absolute filtered amplitude is retained.

Generic Periodic Detector
-------------------------

Non-ECG periodic signals use a generic detector.

The generic pipeline:

1. Detrends the selected segment.
2. Finds positive peaks.
3. Finds negative peaks.
4. Applies minimum spacing based on maximum configured rate.
5. Uses prominence relative to signal standard deviation.
6. Scores positive and negative sequences.
7. Selects the stronger plausible sequence.

The sequence score uses peak prominence and detected peak count.

Generic results should be labeled ``cycles/min`` unless the signal has a validated cardiac interpretation.

Rate Calculation
----------------

Accepted peak times are converted into consecutive intervals:

.. code-block:: text

   intervals = diff(peak_times)

The implementation calculates:

.. code-block:: text

   average interval = mean(intervals)

   median interval = median(intervals)

   interval count = number of detected peaks - 1

   estimated rate =
       60 × interval count
       ÷ (last peak time - first peak time)

The calculated rate is displayed as BPM for ECG sources and cycles/min for generic sources.

Measurement Status
------------------

The current status evaluates timing consistency, not physiological correctness.

``Unable``
   Used when fewer than two peaks are detected, no valid intervals exist, sampling frequency cannot be estimated, or the selection is otherwise invalid.

``Review``
   Used when only one interval is available, the calculated rate is outside configured limits, or interval timing suggests possible irregularity or missed/double detections.

``Timing Consistent``
   Used when multiple detected intervals are within configured rate limits and interval variability is sufficiently low.

The current consistency calculation uses the interval coefficient of variation:

.. code-block:: text

   interval variation =
       standard deviation of intervals
       ÷ mean interval

A typical threshold is:

.. code-block:: text

   interval variation <= 0.20

.. warning::

   Timing consistency does not establish that detected points are true QRS complexes.

   Periodic CPR artifact, pacing spikes, T waves, or repetitive noise may produce a consistent but incorrect detected sequence.

If the UI or older code uses the label ``Reliable``, it should be interpreted or renamed as ``Timing Consistent``.

Temporary Peak Graphics
-----------------------

Accepted peaks are displayed with a ``ScatterPlotItem`` on the selected source waveform.

Peak graphics:

- Use absolute epoch X coordinates.
- Use original source-signal Y values.
- Appear only on the calculation waveform.
- Are removed when markers move.
- Are recalculated after dragging finishes.
- Are removed when source changes or calipers are disabled.
- Are not persisted.

Projection Semantics
--------------------

Projection is independent of peak detection.

Projection spacing is the complete manually selected caliper duration:

.. code-block:: text

   projection spacing =
       absolute(caliper_end_time - caliper_start_time)

For calipers positioned at relative seconds 60 and 65:

.. code-block:: text

   spacing = 5 seconds

Projection positions are:

.. code-block:: text

   backward:
       caliper_start - n × spacing

   forward:
       caliper_end + n × spacing

where ``n`` begins at 1.

The original start and end positions are not duplicated as projection lines.

Projection Rendering
--------------------

Projection markers are rendered only for the current visible X-range, with a small interval buffer.

This prevents the app from creating thousands of off-screen graphics for long recordings.

The implementation:

1. Reads the visible X-range from the first linked plot.
2. Calculates required backward and forward interval counts.
3. Generates absolute epoch positions.
4. Filters positions to loaded waveform bounds.
5. Creates dotted ``InfiniteLine`` items across all plots.
6. Retains references for efficient cleanup.

Projection is recalculated when:

- Either caliper moves.
- Calipers are reset.
- Projection is enabled.
- The user pans.
- The user zooms.

Peak detection is not rerun during ordinary panning or zooming.

Projection Performance Safeguard
--------------------------------

A maximum visible marker count prevents excessive graphics creation.

If the maximum is exceeded:

- Projection markers are temporarily hidden.
- The control indicates that the user should zoom in.
- The selected caliper range remains unchanged.
- Markers return after the visible range becomes smaller.

Projection updates use a short single-shot debounce timer.

Graphics Lifecycle
------------------

Caliper graphics must be removed before plot data is replaced.

Temporary graphics include:

- Primary start/end lines.
- Mirrored start/end lines.
- Peak dots.
- Projection lines.

A new subject load should:

1. Disable and clear calipers.
2. Clear the source dropdown.
3. Replace waveform arrays.
4. Rebuild plots.
5. Repopulate eligible sources.

Annotation-graphics cleanup must not remove items marked as caliper graphics.

Persistence
-----------

Caliper state is intentionally excluded from:

- ``self.annotations``
- annotation dictionaries
- annotation table rows
- partial CSV files
- complete CSV files
- autosave
- terminal completion metadata

No caliper result should affect waveform completion.

Performance Instrumentation
---------------------------

Caliper callbacks follow the existing wrapper/implementation convention.

Examples:

.. code-block:: text

   public_timed_wrapper()
       -> private_implementation()

Performance output uses the existing ``[PERF]`` logger.

Useful measurements include:

- Source dropdown population time.
- Marker drawing time.
- Drag-finished handling time.
- Selected sample count.
- Sampling frequency.
- Detector type.
- Peak-detection time.
- Peak-dot drawing time.
- Projection-marker count.
- Projection rendering time.
- Total measurement-update time.

Expected calculations over short selected segments should complete quickly and operate entirely in memory.

Recommended Testing
-------------------

Test at minimum:

- Upright ECG.
- Inverted ECG.
- Regular rhythm.
- Irregular rhythm.
- Tachycardia.
- Bradycardia.
- Wide complexes.
- Pacing spikes.
- CPR artifact.
- Flat signal.
- Noisy signal.
- Missing samples.
- Non-ECG periodic waveform.
- Marker crossover.
- Calipers outside the visible range.
- Fast pan and zoom.
- Projection at narrow and wide scales.
- Subject changes.
- Annotation clicks with Adjust on and off.

Clinical validation should be performed before describing the estimated rate as diagnostically reliable.
