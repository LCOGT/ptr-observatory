from ptr_utility import plog
from global_yard import g_dev
from astropy.coordinates import SkyCoord, AltAz, get_body, Distance
from astropy.time import Time
from astropy import units as u
from datetime import datetime


def is_valid_utc_iso(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ") is not None
    except ValueError:
        return False

def compute_target_coordinates(target: dict) -> dict:
    """ Apply proper motion and parallax to the target coordinates to get the observed position.
    Reference: https://docs.astropy.org/en/stable/coordinates/apply_space_motion.html

    Input dict should have the following
        ra: float, right ascension in degrees
        dec: float, declination in degrees
        proper_motion_ra: float, proper motion in right ascension in mas/yr
        proper_motion_dec: float, proper motion in declination in mas/yr
        parallax: float, parallax in mas
        epoch: float, epoch in Julian years
    Output dict will have the following
        ra: float, right ascension in hours
        dec: float, declination in degrees
    """

    # Define target parameters
    ra = target.get('ra') * u.deg
    dec = target.get('dec') * u.deg
    pm_ra = target.get('proper_motion_ra', 0) * u.mas/u.yr
    pm_dec = target.get('proper_motion_dec', 0) * u.mas/u.yr
    parallax = target.get('parallax', 0) * u.mas
    epoch = Time(target.get('epoch', 2000), format='jyear')
    observation_time = Time.now()
    distance = Distance(parallax=parallax) if parallax > 0 else None

    # Define the target's initial position
    target = SkyCoord(ra=ra,
                     dec=dec,
                     distance=distance,
                     pm_ra_cosdec=pm_ra,
                     pm_dec=pm_dec,
                     obstime=epoch)

    # Apply proper motion to calculate position at the observation time
    target_observed = target.apply_space_motion(new_obstime=observation_time)

    # Return with ra in hours (0 to 24) and dec in degrees (-90 to 90)
    return {'ra': target_observed.ra.hour, 'dec': target_observed.dec.degree}


def validate_project_format(project):
    """ Ensure that a project is properly formed before attempting to execute it."""
    required_keys = {
        "project_name": str,
        "created_at": str,
        "expiry_date": str,
        "exposures": list,
        "project_constraints": dict,
        "project_creator": dict,
        "project_data": list,
        "project_note": str,
        "project_priority": str,
        "project_sites": list,
        "project_targets": list,
        "remaining": list,
        "scheduled_with_events": list,
        "start_date": str,
        "user_id": str,
    }
    def validate_exposure(exposure):
        required_exposure_keys = {
            "angle": (int, float),
            "count": int,
            "exposure": (int, float),
            "filter": str,
            "imtype": str,
            "zoom": str,
            "offset_ra": (int, float),
            "offset_dec": (int, float)
        }
        return all(key in exposure and isinstance(exposure[key], types)
                   for key, types in required_exposure_keys.items())
    def validate_project_target(target):
        required_target_keys = {
            "name": str,
            "ra": (int, float),
            "dec": (int, float),
        }
        return all(key in target and isinstance(target[key], types)
                   for key, types in required_target_keys.items())
    # Validate top-level keys
    missing_keys = [key for key in required_keys if key not in project]
    if missing_keys:
        return False, f"Missing keys: {missing_keys}"
    # Validate exposures
    exposures = project.get("exposures", [])
    if not exposures or not all(isinstance(exp, dict) and validate_exposure(exp) for exp in exposures):
        return False, "Exposures must be a non-empty list of dictionaries with correct format"
    # Validate project targets
    project_targets = project.get("project_targets", [])
    if not project_targets or not all(isinstance(target, dict) and validate_project_target(target) for target in project_targets):
        return False, "Project targets must be a non-empty list of dictionaries with correct format"
    # Validate project_sites, project_data, and remaining
    if not project.get("project_sites", []):
        return False, "Project sites must be a non-empty list"
    if not project.get("project_data", []):
        return False, "Project data must be a non-empty list"
    if not project.get("remaining", []):
        return False, "Remaining must be a non-empty list"
    return True, "Valid format"

def pointing_is_ok(block, config) -> bool:
    """ Check the target of an observing block that is about to run to make sure the
    requested pointing is observable. """

    pointing_ok = True

    # If the block comes from the scheduler, it should have already vetted the pointing,
    # so assume the pointing is fine.
    # Even if the scheduler is wrong, let's not override it and risk making the bugs
    # harder to track.
    if block.get('origin', 'PTR') == 'LCO':
        plog('Skipping pointing check for LCO block')
        return pointing_ok

    # If a block is identified, check it is in the sky and not in a poor location
    target=block['project']['project_targets'][0]
    ra = float(target['ra'])
    dec = float(target['dec'])
    temppointing=SkyCoord(ra*u.hour, dec*u.degree, frame='icrs')
    temppointingaltaz=temppointing.transform_to(AltAz(location=g_dev['mnt'].site_coordinates, obstime=Time.now()))
    alt = temppointingaltaz.alt.degree

    # Check the moon isn't right in front of the project target
    moon_coords=get_body("moon", time=Time.now())
    moon_dist = moon_coords.separation(temppointing)
    if moon_dist.degree <  config['closest_distance_to_the_moon']:
        g_dev['obs'].send_to_user("Not running project as it is too close to the moon: " + str(moon_dist.degree) + " degrees.")
        plog("Not running project as it is too close to the moon: " + str(moon_dist.degree) + " degrees.")
        pointing_ok = False
    if alt < config['lowest_requestable_altitude']:
        g_dev['obs'].send_to_user("Not running project as it is too low: " + str(alt) + " degrees.")
        plog("Not running project as it is too low: " + str(alt) + " degrees.")
        pointing_ok = False
    return pointing_ok
