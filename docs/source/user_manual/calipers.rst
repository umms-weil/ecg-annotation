.. _calipers:

Using Waveform Calipers
=======================

Overview
--------

The Calipers feature provides a temporary waveform measurement tool.

It can be used to:

- Select a time interval on a waveform.
- Automatically identify repeating waveform peaks inside that interval.
- Estimate a heart rate or periodic cycle rate.
- Display detected peaks for visual review.
- Repeat the complete selected caliper range across the visible waveform as projection markers.
- Compare timing patterns across all displayed waveforms.

.. important::

   Caliper results are measurement aids only. Always visually review the detected peak dots and the underlying waveform.

   Abnormal rhythms, CPR artifact, pacing, noise, low-amplitude signals, and other peri-arrest conditions may cause incorrect or missed peak detections.

Temporary Measurements
----------------------

Caliper measurements are temporary.

The following are **not** saved:

- Caliper start and end positions.
- Detected peak dots.
- Calculated rate.
- Projection markers.
- Measurement status.

Caliper information is **not** added to:

- The annotation table.
- Annotation CSV files.
- Autosave files.
- Final waveform completion metadata.

Caliper Controls
----------------

The Calipers toolbar appears above the waveform plots.

``Calipers ON/OFF``
   Shows or hides the caliper feature.

``Adjust ON/OFF``
   Controls whether the caliper markers can be dragged.

``Source``
   Selects the waveform used for peak detection and rate calculation.

``Projection ON/OFF``
   Shows or hides repeated markers based on the complete selected caliper range.

``Reset``
   Moves the calipers to the center of the current visible time window.

``Result box``
   Displays the selected source, detected peak count, estimated rate, and measurement status.

Turning Calipers On
-------------------

To begin:

1. Load a waveform record.
2. Navigate to the waveform section you want to evaluate.
3. Select a waveform from the **Source** dropdown.
4. Click **Calipers OFF** to turn the feature on.
5. The start and end markers will appear near the center of the current visible time window.

Turning calipers on resets their positions to the current view.

This makes it easy to recover calipers that have moved outside the visible window.

Selecting the Source Waveform
-----------------------------

The source waveform is the signal used for:

- Automatic peak detection.
- Temporary peak-dot placement.
- Rate calculation.

The source dropdown includes only configured waveforms that contain usable data in the current record.

The source may include ECG and non-ECG physiological waveforms, depending on the available data.

Peak dots appear only on the selected source waveform.

The caliper start, end, and projection lines appear across all waveform plots so simultaneous signal behavior can be compared.

Adjusting the Calipers
----------------------

To move the start or end marker:

1. Turn **Adjust ON**.
2. Move the pointer over either caliper line.
3. Click and drag the line to the desired waveform position.
4. Release the line to update the peak detection and rate calculation.
5. Turn **Adjust OFF** when finished.

While **Adjust ON** is active:

- Caliper lines can be dragged.
- Normal annotation endpoint clicks are temporarily ignored.
- Existing annotation state is not changed.

While **Adjust OFF** is active:

- Caliper lines remain visible.
- Caliper lines cannot be moved.
- Normal annotation marking resumes.

Marker Position and Navigation
------------------------------

Caliper markers are attached to waveform time.

When you pan or zoom:

- The markers remain at their selected waveform times.
- The waveform and markers move together.
- A marker may move outside the visible window.
- The selected duration and calculated result remain unchanged.

The markers are not fixed to a location on the computer screen.

To return the calipers to the current view:

- Click **Reset**, or
- Turn Calipers off and back on.

Understanding the Caliper Lines
-------------------------------

The two primary caliper lines define the selected interval.

The earlier marker is treated as the start, even if the markers are dragged past one another.

The selected duration is:

.. code-block:: text

   selected duration = later caliper time - earlier caliper time

The app stores the marker positions internally as high-resolution epoch timestamps.

The waveform plot displays time relative to the beginning of the loaded recording. This display conversion does not change the measurement.

Detected Peak Dots
------------------

After a marker is released, the app analyzes the selected source waveform between the two calipers.

Temporary dots are placed at detected waveform peaks.

Use the dots to confirm that the app selected the intended waveform events.

For ECG signals, the dots should generally align with corresponding QRS or R-wave events.

For other periodic physiological signals, the dots should align with the repeating waveform cycles used for the measurement.

.. warning::

   Regularly spaced artifact can be mistaken for cardiac or physiological activity.

   For example, CPR compressions, pacing spikes, repetitive noise, or T waves may produce regularly spaced detections. A plausible rate does not guarantee that the dots represent true heartbeats.

Estimated Rate
--------------

If at least two usable peaks are detected, the app calculates peak-to-peak intervals.

The estimated rate is based on the number of detected intervals and the elapsed time between the first and last accepted peaks:

.. code-block:: text

   estimated rate =
       60 × number of peak-to-peak intervals
       ÷ elapsed time between first and last accepted peaks

For configured ECG waveforms, the result is displayed in beats per minute:

.. code-block:: text

   BPM

For other periodic waveforms, the result may be displayed as:

.. code-block:: text

   cycles/min

Example result:

.. code-block:: text

   II | 6 peaks | 77.0 BPM | Timing Consistent

Interpreting the Measurement Status
-----------------------------------

The measurement status describes the internal consistency of the detected peak sequence. It does not establish that the detected peaks are clinically correct.

``Timing Consistent``
   The detected peak intervals are within the configured rate range and have relatively consistent timing.

``Review``
   The result was calculated, but the interval pattern is irregular, only one interval is available, or possible missed/double detections may be present.

``Unable``
   The app could not calculate a usable rate. This may occur when fewer than two peaks are detected, the selection is too short, or the signal does not contain enough usable data.

.. important::

   A status of ``Timing Consistent`` means only that the detected dots form a consistent timing sequence.

   It does not guarantee that the dots represent true QRS complexes or cardiac beats.

   Always verify the detected dots visually.


Projection Markers
------------------

Projection markers repeat the complete manually selected caliper duration.

Projection is separate from peak detection and heart-rate calculation.

For example, if the calipers select the range from 60 seconds to 65 seconds:

.. code-block:: text

   Selected duration: 5 seconds

The projected markers appear at:

.. code-block:: text

   ..., 45, 50, 55, [60 ----- 65], 70, 75, 80, ...

Markers project:

- Backward from the start caliper.
- Forward from the end caliper.
- Across all displayed waveform plots.

No additional projection markers are inserted inside the original selected interval.

Using Projection
----------------

To use projection:

1. Turn Calipers on.
2. Adjust the start and end markers.
3. Click **Projection OFF** to turn projection on.
4. Pan through the waveform to compare repeating intervals.
5. Turn projection off when the additional markers are no longer needed.

Projection markers are visual references only.

They can help identify:

- Timing drift.
- Early waveform events.
- Late waveform events.
- Changes in periodicity.
- Loss of alignment across time.
- Differences among simultaneous physiological waveforms.

Projection does not automatically classify or annotate any event.

Projection While Panning and Zooming
------------------------------------

Projection markers are generated for the currently visible time range.

When you pan or zoom:

- The selected caliper interval remains unchanged.
- Peak detection is not rerun unless a caliper marker moves.
- Visible projection markers are updated for the new view.
- Off-screen projection markers are not unnecessarily drawn.

If too many projection markers would be required, the app may temporarily ask you to zoom in.

Resetting the Calipers
----------------------

Click **Reset** to:

- Move both markers to the center of the current visible window.
- Clear previous peak dots.
- Recalculate the selected interval.
- Recalculate the estimated rate.
- Update projection spacing.

Reset does not change existing annotations.

Turning Calipers Off
--------------------

Turning Calipers off removes:

- Start and end markers.
- Detected peak dots.
- Projection markers.
- The displayed temporary result.

Turning them back on creates a new centered selection in the current visible window.

Recommended Use
---------------

For best results:

- Select a waveform with clearly visible repeating events.
- Include multiple cycles when possible.
- Place the boundaries around the area of interest.
- Confirm every detected dot visually.
- Try another available lead if one signal is noisy.
- Use projection as a visual timing guide, not as an annotation.
- Treat ``Review`` and ``Unable`` results cautiously.
- Treat ``Timing Consistent`` as a description of timing consistency only.

Known Limitations
-----------------

Automatic peak detection may be inaccurate with:

- CPR compression artifact.
- Ventricular fibrillation.
- Asystole or near-flat signals.
- Wide-complex rhythms.
- Paced rhythms and pacing spikes.
- Frequent premature beats.
- Low-amplitude ECG.
- Electrode motion.
- Repetitive monitor artifact.
- Highly irregular rhythms.
- Missing waveform samples.
- Very short selected intervals.

Failure to calculate a rate does not imply an absence of cardiac activity.