import streamlit as st
import pyedflib
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import zipfile
import os
import io

st.set_page_config(
    page_title="EDF Protocol Chunker",
    page_icon="✂️",
    layout="wide"
)

st.title("EDF Protocol Chunker")

st.write(
    "Upload the four sensor EDF files, enter the 6MWT and treadmill "
    "start/end times, and extract both protocols from each sensor."
)


# ============================================================
# FUNCTIONS
# ============================================================

def parse_time(time_string, recording_date):
    """
    Convert HH:MM:SS or HH:MM:SS.sss into a datetime.
    The EDF recording date is automatically added.
    """

    time_string = time_string.strip()

    formats = [
        "%H:%M:%S.%f",
        "%H:%M:%S",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(time_string, fmt)
            return datetime.combine(recording_date, parsed.time())
        except ValueError:
            continue

    raise ValueError(
        f"Could not read time '{time_string}'. "
        "Use HH:MM:SS or HH:MM:SS.sss"
    )


def get_file_info(file_path):
    """
    Read basic information from an EDF.
    """

    reader = pyedflib.EdfReader(str(file_path))

    info = {
        "start": reader.getStartdatetime(),
        "duration": reader.file_duration,
        "signals": reader.signals_in_file,
        "end": reader.getStartdatetime()
        + timedelta(seconds=reader.file_duration)
    }

    reader.close()

    return info

def extract_segment(input_path, output_path, segment_start, segment_end):
    """
    Extract a time segment from an EDF and save it as a new EDF.
    """

    reader = pyedflib.EdfReader(str(input_path))

    try:
        file_start = reader.getStartdatetime()
        signal_headers = reader.getSignalHeaders()
        n_signals = reader.signals_in_file

        # ----------------------------------------------------
        # Determine segment indices for each signal
        # ----------------------------------------------------

        segments = []

        for signal_number in range(n_signals):

            sampling_frequency = reader.getSampleFrequency(
                signal_number
            )

            signal = reader.readSignal(signal_number)

            start_index = int(
                round(
                    (segment_start - file_start).total_seconds()
                    * sampling_frequency
                )
            )

            end_index = int(
                round(
                    (segment_end - file_start).total_seconds()
                    * sampling_frequency
                )
            )

            # Keep indices inside the EDF
            start_index = max(0, start_index)
            end_index = min(len(signal), end_index)

            if end_index <= start_index:
                raise ValueError(
                    f"No data available for signal "
                    f"{signal_number} in selected interval."
                )

            segment = signal[start_index:end_index]

            segments.append(
                np.asarray(segment, dtype=np.float64)
            )

        # ----------------------------------------------------
        # Create new EDF
        # ----------------------------------------------------

        writer = pyedflib.EdfWriter(
            str(output_path),
            n_signals,
            file_type=pyedflib.FILETYPE_EDFPLUS
        )

        try:

            writer.setSignalHeaders(signal_headers)

            # Set the new EDF start time
            writer.setStartdatetime(segment_start)

            # Write each signal
            for signal_number in range(n_signals):

                writer.writePhysicalSamples(
                    segments[signal_number]
                )

        finally:
            writer.close()

    finally:
        reader.close()
def create_zip(files):
    """
    Create a ZIP file containing all extracted EDFs.
    """

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(
        zip_buffer,
        "w",
        zipfile.ZIP_DEFLATED
    ) as zip_file:

        for file_path in files:
            zip_file.write(
                file_path,
                arcname=Path(file_path).name
            )

    zip_buffer.seek(0)

    return zip_buffer


# ============================================================
# UPLOAD FILES
# ============================================================

st.header("1. Upload sensor EDF files")

col1, col2 = st.columns(2)

with col1:

    right_wrist = st.file_uploader(
        "Right Wrist EDF",
        type=["edf"],
        key="right_wrist"
    )

    right_ankle = st.file_uploader(
        "Right Ankle EDF",
        type=["edf"],
        key="right_ankle"
    )

with col2:

    left_wrist = st.file_uploader(
        "Left Wrist EDF",
        type=["edf"],
        key="left_wrist"
    )

    left_ankle = st.file_uploader(
        "Left Ankle EDF",
        type=["edf"],
        key="left_ankle"
    )


uploaded_files = {
    "right_wrist": right_wrist,
    "right_ankle": right_ankle,
    "left_wrist": left_wrist,
    "left_ankle": left_ankle
}


# ============================================================
# CHECK THAT ALL FOUR FILES ARE UPLOADED
# ============================================================

if all(uploaded_files.values()):

    st.success("All four sensor files uploaded.")

    temp_dir = Path(tempfile.mkdtemp())

    input_paths = {}

    for sensor, uploaded_file in uploaded_files.items():

        path = temp_dir / f"{sensor}.edf"

        with open(path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        input_paths[sensor] = path


    # ========================================================
    # DISPLAY EDF INFORMATION
    # ========================================================

    st.header("2. EDF recording information")

    file_info = {}

    for sensor, path in input_paths.items():

        try:
            file_info[sensor] = get_file_info(path)

        except Exception as e:

            st.error(
                f"Could not read {sensor}: {e}"
            )


    if file_info:

        for sensor, info in file_info.items():

            st.write(
                f"**{sensor.replace('_', ' ').title()}**  \n"
                f"Start: `{info['start'].strftime('%Y-%m-%d %H:%M:%S')}`  \n"
                f"End: `{info['end'].strftime('%Y-%m-%d %H:%M:%S')}`  \n"
                f"Signals: `{info['signals']}`"
            )


    # ========================================================
    # CHECK SYNCHRONIZATION
    # ========================================================

    starts = [
        info["start"]
        for info in file_info.values()
    ]

    if len(starts) == 4:

        start_range = max(starts) - min(starts)

        if start_range.total_seconds() == 0:

            st.success(
                "✓ All four EDF files have the same start time."
            )

        else:

            st.warning(
                "⚠️ The four EDF files do not have identical "
                "start times. The extraction will use each EDF's "
                "own timestamp."
            )

            st.write(
                f"Maximum start-time difference: "
                f"{start_range.total_seconds():.3f} seconds"
            )


    def plot_edf_accelerometer(
            input_path,
            segment_start,
            segment_end,
            max_points=30000
    ):
        """
        Interactive Plotly visualization of accelerometer X/Y/Z
        using the actual EDF clock time on the x-axis.
        """

        import plotly.graph_objects as go

        reader = pyedflib.EdfReader(str(input_path))

        file_start = reader.getStartdatetime()
        file_end = file_start + timedelta(
            seconds=reader.file_duration
        )

        # --------------------------------------------------------
        # Validate interval
        # --------------------------------------------------------

        if segment_start < file_start:
            reader.close()
            raise ValueError(
                "Selected start time occurs before the EDF recording."
            )

        if segment_end > file_end:
            reader.close()
            raise ValueError(
                "Selected end time occurs after the EDF recording."
            )

        # --------------------------------------------------------
        # Find accelerometer channels
        # --------------------------------------------------------

        accelerometer_signals = []

        for signal_number in range(reader.signals_in_file):

            label = reader.getLabel(signal_number).lower()

            if "accelerometer" in label:
                accelerometer_signals.append(
                    signal_number
                )

        if not accelerometer_signals:
            reader.close()
            raise ValueError(
                "No accelerometer channels were found."
            )

        # --------------------------------------------------------
        # Create figure
        # --------------------------------------------------------

        fig = go.Figure()

        for signal_number in accelerometer_signals:

            fs = reader.getSampleFrequency(
                signal_number
            )

            # ----------------------------------------------------
            # Convert actual clock times to sample indices
            # ----------------------------------------------------

            start_index = int(
                np.floor(
                    (segment_start - file_start).total_seconds()
                    * fs
                )
            )

            end_index = int(
                np.ceil(
                    (segment_end - file_start).total_seconds()
                    * fs
                )
            )

            start_index = max(
                0,
                start_index
            )

            end_index = min(
                reader.getNSamples()[signal_number],
                end_index
            )

            n_samples = end_index - start_index

            if n_samples <= 0:
                continue

            # ----------------------------------------------------
            # Read signal
            # ----------------------------------------------------

            signal = reader.readSignal(
                signal_number,
                start=start_index,
                n=n_samples
            )

            # ----------------------------------------------------
            # Construct ACTUAL timestamps
            # ----------------------------------------------------

            sample_times = [
                segment_start + timedelta(
                    seconds=i / fs
                )
                for i in range(len(signal))
            ]

            # ----------------------------------------------------
            # Downsample display only
            # ----------------------------------------------------

            if len(signal) > max_points:
                step = int(
                    np.ceil(
                        len(signal) / max_points
                    )
                )

                sample_times = sample_times[::step]
                signal = signal[::step]

            # ----------------------------------------------------
            # Plot
            # ----------------------------------------------------

            label = reader.getLabel(
                signal_number
            )

            fig.add_trace(
                go.Scattergl(
                    x=sample_times,
                    y=signal,
                    mode="lines",
                    name=label,
                    line=dict(width=1),
                    hovertemplate=(
                            "%{x|%H:%M:%S.%L}"
                            "<br>"
                            "%{y:.3f}"
                            "<extra>"
                            + label
                            + "</extra>"
                    )
                )
            )

        reader.close()

        # --------------------------------------------------------
        # Layout
        # --------------------------------------------------------

        fig.update_layout(
            title=(
                f"{Path(input_path).stem} — "
                f"Accelerometer"
            ),

            xaxis_title="Time",

            yaxis_title="Acceleration",

            hovermode="x unified",

            height=600,

            margin=dict(
                l=60,
                r=30,
                t=70,
                b=60
            ),

            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0
            )
        )

        # --------------------------------------------------------
        # Force displayed range to requested protocol
        # --------------------------------------------------------

        fig.update_xaxes(
            range=[
                segment_start,
                segment_end
            ],
            rangeslider_visible=True,
            tickformat="%H:%M:%S"
        )

        return fig

    # ========================================================
    # PROTOCOL TIMES
    # ========================================================

    st.header("3. Enter protocol times")

    recording_date = list(file_info.values())[0]["start"].date()

    st.caption(
        f"Enter times using HH:MM:SS. "
        f"Recording date: {recording_date}"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.subheader("6-Minute Walk Test (6MWT)")

        mwt_start_text = st.text_input(
            "6MWT Start Time",
            placeholder="09:15:30"
        )

        mwt_end_text = st.text_input(
            "6MWT End Time",
            placeholder="09:21:30"
        )

    with col2:

        st.subheader("Treadmill Protocol")

        treadmill_start_text = st.text_input(
            "Treadmill Start Time",
            placeholder="09:30:00"
        )

        treadmill_end_text = st.text_input(
            "Treadmill End Time",
            placeholder="09:45:00"
        )
    # ========================================================
    # SIGNAL VISUALIZER
    # ========================================================

    st.header("4. Signal Visualizer")

    st.write(
        "Use the interactive plot to verify the selected "
        "6MWT or treadmill interval. Only accelerometer "
        "signals are displayed."
    )

    visualizer_col1, visualizer_col2 = st.columns(2)

    with visualizer_col1:

        selected_sensor = st.selectbox(
            "Sensor",
            options=list(input_paths.keys()),
            format_func=lambda x: x.replace(
                "_", " "
            ).title(),
            key="visualizer_sensor"
        )

    with visualizer_col2:

        selected_protocol = st.selectbox(
            "Protocol",
            options=["6MWT", "Treadmill"],
            key="visualizer_protocol"
        )

    # --------------------------------------------------------
    # Select protocol times
    # --------------------------------------------------------

    if selected_protocol == "6MWT":

        visualizer_start_text = mwt_start_text
        visualizer_end_text = mwt_end_text

    else:

        visualizer_start_text = treadmill_start_text
        visualizer_end_text = treadmill_end_text

    # --------------------------------------------------------
    # Plot button
    # --------------------------------------------------------

    if st.button(
            "Plot Accelerometer",
            type="secondary"
    ):

        try:

            if not visualizer_start_text.strip():
                raise ValueError(
                    "Please enter a start time."
                )

            if not visualizer_end_text.strip():
                raise ValueError(
                    "Please enter an end time."
                )

            visualizer_start = parse_time(
                visualizer_start_text,
                recording_date
            )

            visualizer_end = parse_time(
                visualizer_end_text,
                recording_date
            )

            if visualizer_end <= visualizer_start:
                raise ValueError(
                    "End time must be after start time."
                )

            selected_path = input_paths[
                selected_sensor
            ]

            selected_info = file_info[
                selected_sensor
            ]

            if visualizer_start < selected_info["start"]:
                raise ValueError(
                    "Start time occurs before the EDF recording."
                )

            if visualizer_end > selected_info["end"]:
                raise ValueError(
                    "End time occurs after the EDF recording."
                )

            with st.spinner(
                    "Loading accelerometer..."
            ):

                fig = plot_edf_accelerometer(
                    selected_path,
                    visualizer_start,
                    visualizer_end
                )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

            duration = (
                    visualizer_end - visualizer_start
            ).total_seconds()

            st.success(
                f"{selected_protocol} | "
                f"{selected_sensor.replace('_', ' ').title()} | "
                f"{duration:.1f} seconds"
            )

        except Exception as e:

            st.error(
                f"Could not plot signal: {e}"
            )
    # ========================================================
    # EXTRACT BUTTON
    # ========================================================

    st.header("5. Extract protocols")

    if st.button(
        "Create 6MWT and Treadmill EDFs",
        type="primary"
    ):

        try:

            # ----------------------------------------------
            # Parse times
            # ----------------------------------------------

            mwt_start = parse_time(
                mwt_start_text,
                recording_date
            )

            mwt_end = parse_time(
                mwt_end_text,
                recording_date
            )

            treadmill_start = parse_time(
                treadmill_start_text,
                recording_date
            )

            treadmill_end = parse_time(
                treadmill_end_text,
                recording_date
            )


            # ----------------------------------------------
            # Validate times
            # ----------------------------------------------

            if mwt_end <= mwt_start:

                raise ValueError(
                    "6MWT end time must be after start time."
                )

            if treadmill_end <= treadmill_start:

                raise ValueError(
                    "Treadmill end time must be after start time."
                )


            # ----------------------------------------------
            # Create output directory
            # ----------------------------------------------

            output_dir = temp_dir / "outputs"

            output_dir.mkdir(
                exist_ok=True
            )


            output_files = []


            # ----------------------------------------------
            # Process all four sensors
            # ----------------------------------------------

            progress_bar = st.progress(0)

            total_operations = 8
            operation = 0


            for sensor, input_path in input_paths.items():

                info = file_info[sensor]

                # ==========================================
                # 6MWT
                # ==========================================

                if (
                    mwt_start < info["start"]
                    or mwt_end > info["end"]
                ):

                    raise ValueError(
                        f"6MWT interval is outside the "
                        f"{sensor} EDF recording."
                    )


                mwt_output = (
                    output_dir
                    / f"{sensor}_6mwt.edf"
                )

                extract_segment(
                    input_path,
                    mwt_output,
                    mwt_start,
                    mwt_end
                )

                output_files.append(
                    mwt_output
                )

                operation += 1
                progress_bar.progress(
                    operation / total_operations
                )


                # ==========================================
                # TREADMILL
                # ==========================================

                if (
                    treadmill_start < info["start"]
                    or treadmill_end > info["end"]
                ):

                    raise ValueError(
                        f"Treadmill interval is outside the "
                        f"{sensor} EDF recording."
                    )


                treadmill_output = (
                    output_dir
                    / f"{sensor}_treadmill.edf"
                )

                extract_segment(
                    input_path,
                    treadmill_output,
                    treadmill_start,
                    treadmill_end
                )

                output_files.append(
                    treadmill_output
                )

                operation += 1
                progress_bar.progress(
                    operation / total_operations
                )


            # =================================================
            # SUCCESS
            # =================================================

            st.success(
                "✓ Successfully created 8 EDF files."
            )


            # =================================================
            # DISPLAY OUTPUTS
            # =================================================

            st.subheader("6MWT files")

            mwt_files = [
                f for f in output_files
                if "_6mwt" in f.name
            ]

            for file_path in mwt_files:

                with open(file_path, "rb") as f:

                    st.download_button(
                        label=f"Download {file_path.name}",
                        data=f.read(),
                        file_name=file_path.name,
                        mime="application/octet-stream",
                        key=f"download_{file_path.name}"
                    )


            st.subheader("Treadmill files")

            treadmill_files = [
                f for f in output_files
                if "_treadmill" in f.name
            ]

            for file_path in treadmill_files:

                with open(file_path, "rb") as f:

                    st.download_button(
                        label=f"Download {file_path.name}",
                        data=f.read(),
                        file_name=file_path.name,
                        mime="application/octet-stream",
                        key=f"download_{file_path.name}"
                    )


            # =================================================
            # ZIP DOWNLOAD
            # =================================================

            st.subheader("Download everything")

            zip_file = create_zip(
                output_files
            )

            st.download_button(
                label="Download all 8 EDF files as ZIP",
                data=zip_file,
                file_name="protocol_EDFs.zip",
                mime="application/zip",
                type="primary"
            )


        except Exception as e:

            st.error(
                f"Error while creating files: {e}"
            )


else:

    st.info(
        "Please upload all four EDF files "
        "to continue."
    )