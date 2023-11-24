"""
Estimation of time variability in a lightcurve
=============
Compute a series of time variability significance estimators for a simulated lightcurve.

Prerequisites
-------------

Understanding the light curve estimator, please refer to the :doc:`light curve notebook </tutorials/analysis-time/light_curve`. For more in-depth explanation on the creation of smaller observations for exploring time variability, refer to :doc:`light curve notebook </tutorials/analysis-time/light_curve_flare`

Context
-------------
Frequently, after computing a lightcurve, we need to quantify its variability in the time domain, for example in the case of a flare, burst, decaying light curve in GRBs or heightened activity in general.

There are many ways to define the significance of the variability.

**Objective: Estimate the level time variability in a lightcurve through different methods.**

Proposed approach
-------------
We will start by computing a lightcurve in the same way as :doc:`light curve notebook </tutorials/analysis-time/light_curve_flare`

On these flux points we will then show the computation of different significance estimators of variability, from the simplest ones based on peak-to-trough varation, to fractional excess variance which takes into account the whole light curve, to a different approach using bayesian blocks.
In summary the steps will be:

-  Create a custom temporal model showing interesting time variability characteristics.
-  Simulate `~gammapy.data.Observations` in 1D according to the model
    as shown in the :doc:`/tutorials/analysis-time/light_curve_simulation` tutorial.
-  Extract the light curve from the reduced dataset as shown
    in :doc:`/tutorials/analysis-time/light_curve` tutorial.
-  Compute the variability significance with methods from 3 different classes: peak-to-trough, fractional excess variance, bayesian blocks.
"""
######################################################################
# Setup
# ----------------------------------------------
# As usual, we’ll start with some general imports…


import logging
import numpy as np
import astropy.units as u
from astropy.coordinates import Angle, SkyCoord
from astropy.stats import bayesian_blocks
from astropy.time import Time
from regions import CircleSkyRegion
import matplotlib.pyplot as plt
from gammapy.data import DataStore
from gammapy.datasets import Datasets, SpectrumDataset
from gammapy.estimators import LightCurveEstimator
from gammapy.estimators.utils import (
    compute_lightcurve_doublingtime,
    compute_lightcurve_fpp,
    compute_lightcurve_fvar,
)
from gammapy.makers import (
    ReflectedRegionsBackgroundMaker,
    SafeMaskMaker,
    SpectrumDatasetMaker,
)
from gammapy.maps import MapAxis, RegionGeom
from gammapy.modeling.models import PowerLawSpectralModel, SkyModel

log = logging.getLogger(__name__)

######################################################################
# We load the data store and perform the same lightcurve computation as in :doc:`light curve notebook </tutorials/analysis-time/light_curve_flare`.


data_store = DataStore.from_dir("$GAMMAPY_DATA/hess-dl3-dr1/")

target_position = SkyCoord(329.71693826 * u.deg, -30.2255890 * u.deg, frame="icrs")
selection = dict(
    type="sky_circle",
    frame="icrs",
    lon=target_position.ra,
    lat=target_position.dec,
    radius=2 * u.deg,
)
obs_ids = data_store.obs_table.select_observations(selection)["OBS_ID"]
observations = data_store.get_observations(obs_ids)
print(f"Number of selected observations : {len(observations)}")

t0 = Time("2006-07-29T20:30")
duration = 10 * u.min
n_time_bins = 35
times = t0 + np.arange(n_time_bins) * duration
time_intervals = [Time([tstart, tstop]) for tstart, tstop in zip(times[:-1], times[1:])]
print(time_intervals[0].mjd)

short_observations = observations.select_time(time_intervals)

######################################################################
# check that observations have been filtered

print(f"Number of observations after time filtering: {len(short_observations)}\n")
print(short_observations[1].gti)

######################################################################
# Target definition
energy_axis = MapAxis.from_energy_bounds("0.4 TeV", "20 TeV", nbin=10)
energy_axis_true = MapAxis.from_energy_bounds(
    "0.1 TeV", "40 TeV", nbin=20, name="energy_true"
)

on_region_radius = Angle("0.11 deg")
on_region = CircleSkyRegion(center=target_position, radius=on_region_radius)

geom = RegionGeom.create(region=on_region, axes=[energy_axis])

dataset_maker = SpectrumDatasetMaker(
    containment_correction=True, selection=["counts", "exposure", "edisp"]
)
bkg_maker = ReflectedRegionsBackgroundMaker()
safe_mask_masker = SafeMaskMaker(methods=["aeff-max"], aeff_percent=10)

datasets = Datasets()

dataset_empty = SpectrumDataset.create(geom=geom, energy_axis_true=energy_axis_true)

for obs in short_observations:
    dataset = dataset_maker.run(dataset_empty.copy(), obs)

    dataset_on_off = bkg_maker.run(dataset, obs)
    dataset_on_off = safe_mask_masker.run(dataset_on_off, obs)
    datasets.append(dataset_on_off)

spectral_model = PowerLawSpectralModel(
    index=3.4, amplitude=2e-11 * u.Unit("1 / (cm2 s TeV)"), reference=1 * u.TeV
)
spectral_model.parameters["index"].frozen = False

sky_model = SkyModel(spatial_model=None, spectral_model=spectral_model, name="pks2155")

datasets.models = sky_model

lc_maker_1d = LightCurveEstimator(
    energy_edges=[0.7, 20] * u.TeV,
    source="pks2155",
    time_intervals=time_intervals,
    selection_optional=None,
)

lc_1d = lc_maker_1d.run(datasets)

plt.figure(figsize=(8, 6))
lc_1d.plot(marker="o")
plt.show()

######################################################################
# # Methods to characterize variability
# ---------------
#  Amplitude maximum variation, relative variability amplitude and variability amplitude
#
# The amplitude maximum variation is the simplest method to define variability ([reference
# paper](https://ui.adsabs.harvard.edu/abs/2016A&A...588A.103B/abstract)) as it just computes the level of tension between the lowest and highest measured fluxes in the lighcurve

flux = lc_1d.flux.data
flux_err = lc_1d.flux_err.data

f_mean = np.mean(flux)
f_mean_err = np.mean(flux_err)

f_max = flux.max()
f_max_err = flux_err[np.argmax(flux)]
f_min = flux.min()
f_min_err = flux_err[np.argmin(flux)]

amplitude_maximum_variation = (f_max - f_max_err) - (f_min - f_min_err)

amplitude_maximum_significance = amplitude_maximum_variation / np.sqrt(
    f_max_err**2 + f_min_err**2
)

print(amplitude_maximum_significance)

# There are other methods based on the peak-to-trough difference to asses the varability in a lighcurve. Here we present as example the relative variability amplitude ([reference paper](https://iopscience.iop.org/article/10.1086/497430)):

relative_variability_amplitude = (f_max - f_min) / (f_max + f_min)

relative_variability_error = (
    2
    * np.sqrt((f_max * f_min_err) ** 2 + (f_min * f_max_err) ** 2)
    / (f_max + f_min) ** 2
)

relative_variability_significance = (
    relative_variability_amplitude / relative_variability_error
)

print(sig_RV_a)

# And the variability amplitude ([reference paper](https://ui.adsabs.harvard.edu/abs/1996A%26A...305...42H/abstract)):

variability_amplitude = np.sqrt((f_max - f_min) ** 2 - 2 * f_mean_err**2)

variability_amplitude_100 = 100 * variability_amplitude / f_mean

variability_amplitude_error = (
    100
    * ((f_max - f_min) / (f_mean * variability_amplitude_100 / 100))
    * np.sqrt(
        (f_max_err / f_mean) ** 2
        + (f_min_err / f_mean) ** 2
        + ((np.std(flux, ddof=1) / np.sqrt(len(flux))) / (f_max - f_mean)) ** 2
        * (variability_amplitude_100 / 100) ** 4
    )
)

variability_amplitude_significance = (
    variability_amplitude_100 / variability_amplitude_error
)

print(variability_amplitude_significance)

######################################################################
#  Fractional excess variance, point-to-point fractional variance and doubling/halving time
# ----------------------------------------------
# The fractional excess variance ([reference
# paper](https://ui.adsabs.harvard.edu/abs/2003MNRAS.345.1271V/abstract)) is a simple but effective method to assess the significance of a time variability feature in an object, for example an AGN flare. It is important to note that it requires gaussian errors to be applicable. The excess variance computation is implemented in the `estimators.utils` subpackage of `gammapy`. A similar estimator is the point-to-point fractional variance, which samples the lightcurve with a smaller time granularity. In general, the point-to-point fractional variance being higher than the fractional excess variance is a sign of the presence of very short timescale variability. The point-to-point variability is also implemented in the `estimators.utils` subpackage of `gammapy`.
#
# In the same subpackage `gammapy` also offers the computation of the doubling and halving time of the lightcurve, an estimator which gives information on the shape of the variability feature.

fvar_table = compute_lightcurve_fvar(lc_1d)
print(fvar_table)

fpp_table = compute_lightcurve_fpp(lc_1d)
print(fpp_table)

dtime_table = compute_lightcurve_doublingtime(lc_1d, flux_quantity="flux")
print(dtime_table)

######################################################################
# ## Bayesian blocks
# ----------------------------------------------
# The presence of temporal variability in a lightcurve can be assessed by using bayesian blocks ([reference
# paper](https://ui.adsabs.harvard.edu/abs/2013ApJ...764..167S/abstract)). A good and simple-to-use implementation of the algorithm is found in `astropy.stats`([documentation](https://docs.astropy.org/en/stable/api/astropy.stats.bayesian_blocks.html)). This implementation uses guassian statistics, as opposed to the [first introductory paper](https://iopscience.iop.org/article/10.1086/306064) which was based on poissonian statistics.
#
# By passing the flux and error on the flux as `measures` to the method we can obtain the list of optimal bin edges defined by the bayesian blocks algorithm.

time = lc_1d.geom.axes["time"].time_mid.mjd

bayesian_edges = Time(
    bayesian_blocks(
        t=time, x=flux.flatten(), sigma=flux_err.flatten(), fitness="measures"
    ),
    format="mjd",
)

# We then can then (optionally) compute the new lightcurve and plot it

time_intervalsB = [
    Time([tstart, tstop])
    for tstart, tstop in zip(bayesian_edges[:-1], bayesian_edges[1:])
]

lc_maker_1d = LightCurveEstimator(
    energy_edges=[0.7, 10] * u.TeV,
    source="pks2155",
    selection_optional=["ul"],
    time_intervals=time_intervalsB,
)

lc_b = lc_maker_1d.run(datasets)

fig, ax = plt.subplots(
    figsize=(8, 6),
    gridspec_kw={"left": 0.16, "bottom": 0.2, "top": 0.98, "right": 0.98},
)

lc_b.plot(marker="o", axis_name="time", sed_type="flux")
lc_1d.plot(marker="o", axis_name="time", sed_type="flux")
plt.legend()
plt.show()

# The result giving a significance estimation for variability in the lighcurve is the number of *change points*, i.e. the number of internal bin edges: if at least one change point is identified by the algorithm, there is significant variability.

ncp = len(bayesian_edges) - 2
print(ncp)
