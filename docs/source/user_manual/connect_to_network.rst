.. _connecting-to-network:

Connecting to VPN and Turbo Storage
===================================

Overview
--------

Waveform data may be stored on U-M Turbo Research Storage. If you are off-site, you may need to connect to the Michigan Medicine / UMHS SSL VPN before accessing Turbo.

This page covers:

- Connecting to the UMHS SSL VPN.
- Connecting to Turbo from Windows File Explorer.
- Connecting to Turbo from macOS Finder.
- Common troubleshooting steps.

.. important::

   Exact VPN and Turbo paths may vary by project. Use the VPN instructions and Turbo storage path provided by your project team, PI, or data manager.

Useful U-M Links
----------------

U-M VPN information:

- `U-M VPN / Remote Access <https://its.umich.edu/enterprise/wifi-networks/vpn>`_

Michigan Medicine / HITS support:

- `Michigan Medicine HITS <https://hits.medicine.umich.edu/>`_

Turbo Research Storage:

- `Advanced Research Computing: Turbo Research Storage <https://documentation.its.umich.edu/node/5038>`_
- `ARC Help and Support <https://docs.support.arc.umich.edu/help/>`_

General U-M IT help:

- `U-M ITS Help <https://its.umich.edu/help>`_

When VPN Is Needed
------------------

You usually need VPN if you are:

- off-site,
- not connected to the Michigan Medicine or U-M network,
- working from home,
- using a non-campus internet connection.

You may not need VPN if you are:

- on-site,
- connected to the appropriate Michigan Medicine or U-M network,
- using a workstation already connected to internal network resources.

.. note::

   VPN access may be slower than working directly on the Michigan Network. Waveform files can be large, so loading subjects may take longer over VPN.

Connecting to the UMHS SSL VPN
------------------------------

Use the official UMHS SSL VPN instructions provided by Michigan Medicine HITS or your project team.

General steps:

1. Open a Cisco App.
2. Connect to the UMHS SSL VPN.
3. Sign in with your U-M credentials.
4. Complete Okta two-factor authentication if prompted.
5. Start the VPN connection.
6. Wait until the VPN reports that it is connected.
7. After VPN connection is established, connect to Turbo storage.

Connecting to Turbo
-------------------

Please follow the Documentation provided here: `Connecting to Turbo <https://documentation.its.umich.edu/node/5039>`

Adding Turbo to Finder Favorites
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After the Turbo volume is mounted:

1. Open the mounted Turbo volume in Finder.
2. Drag the folder to the Finder sidebar under **Favorites**.
3. Use this shortcut in future sessions.

.. note::

   If you are off-site, connect to VPN before using the Finder favorite.

Selecting the Base Folder in the Annotation App
-----------------------------------------------

After Turbo is mounted:

1. Open the ECG Waveform Annotation App.
2. In the app, click **Browse** or paste the base folder path.
3. Select the top-level waveform data folder.
4. Click **Set Folder** if you pasted the path manually.
5. Wait for the subject or waveform record dropdown to populate.

Example Windows mounted path::

   Z:\project\waveforms

Example Windows UNC path::

   \\turbosmb.umich.edu\umms-PI\project\waveforms

Example macOS mounted path::

   /Volumes/umms-PI/project/waveforms

.. important::

   Use the path provided by your project team. Do not guess or manually alter the folder structure.

Performance Tips
----------------

For best performance:

- Use the Michigan Network directly when possible.
- If off-site, connect to VPN before launching the app.
- Avoid loading multiple large waveform files at the same time.
- Be patient when loading large subjects over VPN.
- Do not open waveform files manually while the app is using them.

Troubleshooting
---------------

Cannot Connect to VPN
~~~~~~~~~~~~~~~~~~~~~

Try:

1. Confirm your internet connection is working.
2. Confirm you are using the correct UMHS SSL VPN instructions.
3. Confirm your U-M credentials are working.
4. Complete Duo authentication.
5. Contact HITS if VPN access still fails.

Support:

- `HITS Get Help <https://hits.medicine.umich.edu/get-help>`_

Cannot Connect to Turbo
~~~~~~~~~~~~~~~~~~~~~~~

Try:

1. Confirm VPN is connected if off-site.
2. Confirm the Turbo path is correct.
3. Confirm you have permission to access the Turbo volume.
4. Try disconnecting and reconnecting VPN.
5. Restart Finder or File Explorer.
6. Contact your project team or ARC support.

Support:

- `ARC Help and Support <https://arc.umich.edu/help/>`_

Slow Loading
~~~~~~~~~~~~

Possible causes:

- VPN connection is slow.
- Waveform files are large.
- Network storage is under load.
- The selected waveform record contains a long recording.

Try:

- Wait for the load to complete.
- Use the Michigan Network directly if possible.
- Avoid loading other large network files at the same time.

Access Denied
~~~~~~~~~~~~~

If you receive an access denied or permission error:

1. Confirm you are using your own U-M credentials.
2. Confirm you are connected to VPN if off-site.
3. Confirm your project team has granted you access to the Turbo volume.
4. Contact your project data manager, PI, or ARC support.

Do Not Manually Modify Data Files
---------------------------------

.. warning::

   Do not manually edit, rename, move, or delete waveform files, manifest files, or annotation output files.

   Use the annotation app to load, save, and resume annotation work. Manual file changes may cause data loss, corruption, or incomplete annotation records.