"""
Stations Class

Meteorological data provided by Meteostat (https://dev.meteostat.net)
under the terms of the Creative Commons Attribution-NonCommercial
4.0 International Public License.

The code is licensed under the MIT license.
"""

from math import cos, sqrt, radians
from copy import copy
from datetime import timedelta
import pandas as pd
from meteostat.core import Core

class Stations(Core):

    """
    Select weather stations from the full list of stations
    """

    # The cache subdirectory
    _cache_subdir = 'stations'

    # The list of selected weather Stations
    _stations = None

    # Columns
    _columns = [
        'id',
        'name',
        'country',
        'region',
        'wmo',
        'icao',
        'latitude',
        'longitude',
        'elevation',
        'timezone',
        'hourly_start',
        'hourly_end',
        'daily_start',
        'daily_end'
    ]

    _types = {
        'id': 'string',
        'name': 'object',
        'country': 'string',
        'region': 'string',
        'wmo': 'string',
        'icao': 'string',
        'latitude': 'float64',
        'longitude': 'float64',
        'elevation': 'float64',
        'timezone': 'string'
    }

    # Columns for date parsing
    _parse_dates = [10, 11, 12, 13]

    def __init__(
        self,
        uid=None,
        wmo=None,
        icao=None,
        lat=None,
        lon=None,
        radius=None,
        country=None,
        region=None,
        bounds=None,
        inventory=None,
        config={},
        cache_dir=None,
        max_age=None,
        max_threads=None
    ):

        # Configuration - Cache directory
        if 'cache_dir' in config:
            self._cache_dir = config['cache_dir']

        # Configuration - Maximum file age
        if 'max_age' in config:
            self._max_age = config['max_age']

        # Configuration - Maximum number of threads
        if 'max_threads' in config:
            self._max_threads = config['max_threads']

        # Get all weather stations
        try:
            file = self._load(['stations/lib.csv.gz'])[0]
            self._stations = pd.read_parquet(file['path'])
        except BaseException as read_error:
            raise Exception('Cannot read weather station directory') from read_error

        # Filter by identifier
        if uid is not None or wmo is not None or icao is not None:
            self._identifier(uid, wmo, icao)

        # Filter by country or region
        if country is not None or region is not None:
            self._regional(country, region)

        # Filter by boundaries
        if bounds is not None:
            self._area(bounds)

        # Filter by distance
        if lat is not None and lon is not None:
            self._nearby(lat, lon, radius)

        # Filter by inventory
        if inventory is not None:
            self._inventory(inventory)

        # Clear cache
        self.clear_cache()

    def _identifier(self, uid=None, wmo=None, icao=None):

        """
        Get weather station by identifier
        """

        # Get station by Meteostat ID
        if uid is not None:

            if not isinstance(uid, list):
                uid = [uid]

            self._stations = self._stations[self._stations.index.isin(uid)]

        # Get station by WMO ID
        elif wmo is not None:

            if not isinstance(wmo, list):
                wmo = [wmo]

            self._stations = self._stations[self._stations['wmo'].isin(wmo)]

        # Get stations by ICAO ID
        elif icao is not None:

            if isinstance(icao, list):
                icao = [icao]

            self._stations = self._stations[self._stations['icao'] == icao]

        # Return self
        return self

    def _nearby(self, lat=False, lon=False, radius=None):

        """
        Sort/filter weather stations by physical distance
        """

        # Calculate distance between weather station and geo point
        def distance(station, point):

            # Earth radius in m
            radius = 6371000

            x = (radians(point[1]) - radians(station['longitude'])) * \
                cos(0.5 * (radians(point[0]) + radians(station['latitude'])))
            y = (radians(point[0]) - radians(station['latitude']))

            return radius * sqrt(x * x + y * y)

        # Get distance for each stationsd
        self._stations['distance'] = self._stations.apply(
            lambda station: distance(station, [lat, lon]), axis=1)

        # Filter by radius
        if radius is not None:
            self._stations = self._stations[self._stations['distance'] <= radius]

        # Sort stations by distance
        self._stations.columns.str.strip()
        self._stations = self._stations.sort_values('distance')

        # Return self
        return self

    def _regional(self, country=None, region=None):

        """
        Filter weather stations by country/region code
        """

        # Check if country is set
        if country is not None:
            self._stations = self._stations[self._stations['country'] == country]

        # Check if region is set
        if region is not None:
            self._stations = self._stations[self._stations['region'] == region]

        # Return self
        return self

    def _area(self, bounds=None):

        """
        Filter weather stations by geographical bounds
        """

        # Return stations in boundaries
        if bounds is not None:
            self._stations = self._stations[
                (self._stations['latitude'] <= bounds[0]) &
                (self._stations['latitude'] >= bounds[2]) &
                (self._stations['longitude'] <= bounds[3]) &
                (self._stations['longitude'] >= bounds[1])
            ]

        # Return self
        return self

    def _inventory(self, filter):

        """
        Filter weather stations by inventory data
        """

        for resolution, value in filter.items():
            if value is True:
                # Make sure data exists at all
                self._stations = self._stations[
                    (pd.isna(self._stations[resolution + '_start']) == False)
                ]
            elif isinstance(value, list):
                # Make sure data exists across period
                self._stations = self._stations[
                    (pd.isna(self._stations[resolution + '_start']) == False) &
                    (self._stations[resolution + '_start'] <= value[0]) &
                    (
                        self._stations[resolution + '_end'] +
                        timedelta(seconds=self._max_age)
                        >= value[1]
                    )
                ]
            else:
                # Make sure data exists on a certain day
                self._stations = self._stations[
                    (pd.isna(self._stations[resolution + '_start']) == False) &
                    (self._stations[resolution + '_start'] <= value) &
                    (
                        self._stations[resolution + '_end'] +
                        timedelta(seconds=self._max_age)
                        >= value
                    )
                ]

        return self

    def convert(self, units):

        """
        Convert columns to a different unit
        """

        # Create temporal instance
        temp = copy(self)

        # Change data units
        for parameter, unit in units.items():
            if parameter in temp._columns:
                temp._stations[parameter] = temp._stations[parameter].apply(
                    unit)

        # Return class instance
        return temp

    def count(self):

        """
        Return number of weather stations in current selection
        """

        return len(self._stations.index)

    def fetch(self, limit=False, sample=False):

        """
        Fetch all weather stations or a (sampled) subset
        """

        # Copy DataFrame
        temp = copy(self._stations)

        # Return limited number of sampled entries
        if sample and limit:
            return temp.sample(limit)

        # Return limited number of entries
        if limit:
            return temp.head(limit)

        # Return all entries
        return temp
