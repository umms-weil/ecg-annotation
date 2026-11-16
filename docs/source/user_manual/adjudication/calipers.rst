.. _adjudication-calipers:

Calipers and Temporary Measurements
===================================

Purpose
-------

Calipers support temporary timing measurements during waveform review.

They provide:

- A selected start-to-stop duration.
- Automatic peak detection.
- Manual peak selection.
- Estimated BPM or cycles per minute.
- Projection of the full selected time interval.

Calipers do not change the final adjudication timeline.

.. warning::

   Automatic peak detection is experimental and has not been clinically
   validated for this peri-arrest application.

   CPR artifact, pacing, noise, and abnormal rhythms can produce missed or
   incorrect peaks. Always inspect the dots and underlying waveform.

Temporary State
---------------

The following are not saved in adjudication CSV or JSON files:

- Caliper positions.
- Peak dots.
- Manual dot selections.
- Estimated rates.
- Projection markers.

Changing records clears the measurement.

Controls
--------

``Calipers ON/OFF``
   Shows or clears the temporary measurement.

``Adjust ON/OFF``
   Enables dragging the start and stop markers.

``Source``
   Selects the signal used for automatic or manual peak measurement.

``Reset``
   Recenters the markers in the current visible waveform range.

``Auto Peaks ON/OFF``
   Enables or disables automatic peak detection.

``Manual Label ON/OFF``
   Enables clicking the selected source signal to place manual dots.

``Undo Dot``
   Removes the most recently added manual dot.

``Clear Dots``
   Removes all manual dots.

``Projection ON/OFF``
   Repeats the complete selected caliper duration across the visible waveforms.

``Result``
   Displays temporary duration, peak count, rate, and measurement information.

Positioning the Calipers
-----------------------

1. Navigate to the waveform area of interest.
2. Turn Calipers on.
3. The start and stop markers appear near the center of the visible range.
4. Turn Adjust on.
5. Drag either marker on any displayed waveform.
6. Release the marker.
7. Turn Adjust off when finished.

Marker positions remain attached to waveform time.

Panning and zooming do not change the selected positions.
The markers may move off-screen.

Use Reset, or turn Calipers off and back on, to recover them in the current
view.

Source Selection
----------------

The source determines which signal is measured.

It is independent of the displayed waveform-row selectors.

For manual dot placement, display the selected source in at least one
waveform row.

Peak dots appear on rows displaying that source signal.

Changing the measurement source clears the previous peak selection.

Automatic Measurement
----------------------

With Auto Peaks on, the app analyzes the source samples between the
calipers after marker adjustment finishes.

It displays temporary detected dots and, when at least two peaks are
available, an estimated rate.

The result includes an instruction to verify the dots.

Automatic calculation may be unavailable when:

- SciPy is not installed.
- The selected interval is too short.
- Too few valid samples exist.
- Data gaps are detected.
- The selected interval exceeds the configured processing limit.
- Fewer than two peaks are detected.

The current default automatic selection limit is 120 seconds.

If the range is too large, narrow it or use manual labeling.

Manual Peak Labeling
--------------------

Manual labeling is useful when automatic detections do not match the intended
waveform events.

1. Position the calipers.
2. Select the measurement source.
3. Display that source in a waveform row.
4. Turn Manual Label on.
5. Click equivalent points in successive waveform cycles inside the calipers.
6. Add at least two dots.
7. Inspect the calculated rate.
8. Turn Manual Label off before continuing adjudication clicks.

Each click snaps to the nearest finite waveform sample.

The dot's vertical value comes from the actual signal, not the mouse's
vertical position.

Manual labeling and caliper adjustment cannot be active simultaneously.

Manual Label Off
~~~~~~~~~~~~~~~~

Turning Manual Label off retains the temporary dots and rate.
It returns clicks to normal adjudication behavior.

Correcting Dots
~~~~~~~~~~~~~~

Use Undo Dot to remove the last point added.

Undo follows insertion order, not left-to-right time order.

Use Clear Dots to restart the manual selection.

Duplicate clicks on the same sample do not create additional dots.

Rate Calculation
----------------

Accepted dots are ordered by time.

The calculated rate is::

   intervals = number of peaks - 1

   rate = 60 × intervals
          / (last peak time - first peak time)

For ECG signals, the unit is BPM.
For configured non-ECG signals, it is cycles/min.

Example::

   II | 5 peaks | 75.0 BPM | Manual

Choose corresponding points across cycles.
Mixing different features, such as an R peak followed by a T wave, biases
the measurement.

.. important::

   A calculated ECG rate is not proof of effective circulation.

   A cycles/min result from chest impedance must not automatically be
   interpreted as heart rate.

Range Projection
----------------

Projection repeats the entire caliper duration, not the detected R-R interval.

Example::

   Start caliper: 60 seconds
   Stop caliper:  65 seconds
   Duration:       5 seconds

   Projection:
   ..., 45, 50, 55, [60 ----- 65], 70, 75, 80, ...

Projected markers extend:

- Backward from the earlier caliper.
- Forward from the later caliper.
- Across all displayed waveform rows.

Projection works independently of automatic and manual peak detection.

Panning and Zooming
~~~~~~~~~~~~~~~~~~

Only visible projection markers and a small surrounding buffer are rendered.

Panning updates projection graphics without rerunning peak detection.

If the view would require too many markers, projection is temporarily hidden
and the button requests zooming in.

Zooming in restores the markers.

Interaction with Adjudication
----------------------------

While Adjust or Manual Label is active:

- Final-boundary dragging is suspended.
- Add/Remove Boundary is unavailable.
- Normal adjudication plot-click actions are suppressed.

Turn those modes off before editing final intervals.

Finish or cancel pending Add Boundary placement before entering a caliper
interaction mode.

Clearing Measurements
---------------------

Moving either caliper, resetting, or changing the measurement source clears
manual dots because the measurement context changed.

Changing only a displayed waveform row preserves the caliper positions.
Dots are shown if that row displays the selected source.

Turning Calipers off clears all temporary measurement graphics and values.

Recommended Review
------------------

- Prefer a source with clearly visible repeating events.
- Review every automatic dot.
- Use manual labeling when automatic detection is inappropriate.
- Include multiple complete cycles when possible.
- Treat projection as a visual reference only.
- Turn interactive caliper modes off before returning to final editing.

Related Pages
-------------

- :ref:`adjudication-interface-guide`
- :ref:`adjudication-editing-labels-boundaries`
- :ref:`adjudication-troubleshooting`