import os
import datetime
from flask import (
    Flask,
    request,
    redirect,
    send_file,
    render_template,
    after_this_request,
)
import gpxpy
import geopandas as gpd
from fit_tool.fit_file import FitFile
from fit_tool.profile.messages.record_message import RecordMessage
from pyhigh import get_elevation

app = Flask(__name__)
UPLOAD_FOLDER = "./uploads"
PROCESSED_FOLDER = "./processed"
COURSES_FOLDER = "./courses"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(COURSES_FOLDER, exist_ok=True)


@app.route("/")
def upload_form():
    # Get the list of pre-uploaded GPX courses from the courses directory
    pre_uploaded_courses = [f for f in os.listdir(COURSES_FOLDER) if f.endswith(".gpx")]
    return render_template("upload.html", courses=pre_uploaded_courses)


@app.route("/upload", methods=["POST"])
def upload_file():
    if "fit_file" not in request.files:
        return redirect(request.url)

    fit_file = request.files["fit_file"]
    gpx_file = request.files["gpx_file"]
    selected_course = request.form.get("selected_course")

    if fit_file.filename == "":
        return redirect(request.url)

    # Save the uploaded FIT file
    fit_file_path = os.path.join(UPLOAD_FOLDER, fit_file.filename)
    fit_file.save(fit_file_path)

    # Determine which GPX file to use (uploaded or pre-uploaded)
    if gpx_file and gpx_file.filename != "":
        gpx_file_path = os.path.join(UPLOAD_FOLDER, gpx_file.filename)
        gpx_file.save(gpx_file_path)
    elif selected_course:
        gpx_file_path = os.path.join(COURSES_FOLDER, selected_course)
    else:
        return redirect(request.url)

    # Generate GPX using the provided generate_workout_gpx function
    processed_gpx = generate_workout_gpx(fit_file_path, gpx_file_path)

    # Save the processed GPX to a file
    output_gpx_file = os.path.join(PROCESSED_FOLDER, "processed.gpx")
    with open(output_gpx_file, "w") as f:
        f.write(processed_gpx.to_xml())

    @after_this_request
    def cleanup_files(response):
        try:
            os.remove(fit_file_path)  # Delete uploaded FIT file
            if gpx_file and gpx_file.filename != "":
                os.remove(gpx_file_path)  # Delete uploaded GPX file
            os.remove(output_gpx_file)  # Delete processed GPX file
        except Exception as e:
            print(f"Error deleting files: {e}")
        return response

    return send_file(output_gpx_file, as_attachment=True, download_name="processed.gpx")


def generate_workout_gpx(workout_fit_file_path: str, course_gpx_file_path: str):
    course_gpx = gpd.read_file(course_gpx_file_path, layer="tracks").to_crs(epsg=3310)
    workout = FitFile.from_file(workout_fit_file_path)

    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)

    # Create first segment in our GPX track:
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)

    for record in workout.records:
        message = record.message
        if isinstance(message, RecordMessage) and message.distance is not None:
            point_at_dist = course_gpx.interpolate(
                message.distance % course_gpx.length
            ).to_crs(epsg=4326)

            gpx_segment.points.append(
                gpxpy.gpx.GPXTrackPoint(
                    point_at_dist[0].y,
                    point_at_dist[0].x,
                    elevation=get_elevation(point_at_dist[0].y, point_at_dist[0].x),
                    time=datetime.datetime.fromtimestamp(message.timestamp / 1e3),
                )
            )
    return gpx


if __name__ == "__main__":
    app.run(debug=True)
