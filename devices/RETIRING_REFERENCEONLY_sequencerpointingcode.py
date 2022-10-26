# -*- coding: utf-8 -*-
"""
Created on Sun Oct 23 20:57:11 2022

@author: obs
"""

    def equatorial_pointing_run(self, req, opt, spacing=10, vertical=False, grid=False, alt_minimum=25):
        '''
        unpark telescope
        if not open, open dome
        go to zenith & expose (Consider using Nearest mag 7 grid star.)
        verify reasonable transparency
            Ultimately, check focus, find a good exposure level
        go to -72.5 degrees of ha, 0  expose
        ha += 10; repeat to Ha = 67.5
        += 5, expose
        -= 10 until -67.5

        if vertical go ha = -0.25 and step dec 85 -= 10 to -30 then
        flip and go other way with offset 5 deg.

        For Grid use Patrick Wallace's Mag 7 Tyco star grid it covers
        sky equal-area, has a bright star as target and wraps around
        both axes to better sample the encoders. Choose and load the
        grid coarseness.
        '''
        '''
        Prompt for ACCP model to be turned off
        if closed:
           If WxOk: open
        if parked:
             unpark

         pick grid star near zenith in west (no flip)
              expose 10 s
              solve
              Is there a bright object in field?
              adjust exposure if needed.
        Go to (-72.5deg HA, dec = 0),
             Expose, calibrate, save file.  Consider
             if we can real time solve or just gather.
        step 10 degrees forward untl ha is 77.5
        at 77.5 adjust target to (72.5, 0) and step
        backward.  Stop when you get to -77.5.
        park
        Launch reduction

A variant on this is cover a grid, cover a + sign shape.
IF sweep
        '''
       # ptr_utility.ModelOn = False

        self. sky_guard = True
        ha_deg_steps = (-72.5, -62.5, -52.5, -42.5, -32.5, -22.5, -12.5, -2.5, \
                         -7.5, -17.5, -27.5, -37.5, -47.5, -57.5, -67.5, \
                         2.5,  12.5, 22.5, 32.5, 42.5, 52.5, 62.5, 72.5, \
                         67.5, 57.5, 47.5, 37.5, 27.5, 17.5, 7.5)
        length = len(ha_deg_steps)
        count = 0
        print("Starting equatorial sweep.")
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera_1_1']['name'])
        for ha_degree_value in ha_deg_steps:
            target_ra = ra_fix(g_dev['mnt'].mount.SiderealTime - ha_degree_value/15.)
            target_dec = 0
            #     #  Go to closest Mag 7.5 Tycho * with no flip
            # focus_star = tycho.dist_sort_targets(target_ra, target_dec, \
            #                    g_dev['mnt'].mount.SiderealTime)
            # if focus_star is None:
            #     print("No near star, skipping.")   #This should not happen.
            #     continue
            #print("Going to near focus star " + str(focus_star[0]) + "  degrees away.")
            #req = {'ra':  focus_star[1][1],
            #       'dec': focus_star[1][0]     #Note order in important (dec, ra)
            req = {'ra':  target_ra,
                   'dec': target_dec     #Note order in important (dec, ra)
                   }
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            st = ''
            enc_status = eval(self.redis_server.get('enc_status'))  #NB Is this current?
            while g_dev['mnt'].mount.Slewing or enc_status['dome_slewing']:
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                if g_dev['enc'].status['dome_slewing']: st += 'd>'
                print(st)
                st = ''
                g_dev['obs'].update_status()
                time.sleep(0.5)
            time.sleep(3)
            g_dev['obs'].update_status()
            req = {'time': 10,  'alias': 'sq01', 'image_type': 'experimental'}
            opt = {'area': 150, 'count': 1, 'bin': '2,2', 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Equator Run'}
            result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            result = 'simulated result.'
            count += 1
            print('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')
        g_dev['mnt'].mount.Tracking = False
        print("Equatorial sweep completed. Happy reducing.")
        ptr_utility.ModelOn = True
        self.sky_guard = False
        return

    def cross_pointing_run(self, req, opt, spacing=30, vertical=False, grid=False, alt_minimum=25):
        '''
        unpark telescope
        if not open, open dome
        go to zenith & expose (Consider using Nearest mag 7 grid star.)
        verify reasonable transparency
            Ultimately, check focus, find a good exposure level
        go to -72.5 degrees of ha, 0  expose
        ha += 10; repeat to Ha = 67.5
        += 5, expose
        -= 10 until -67.5

        if vertical go ha = -0.25 and step dec 85 -= 10 to -30 then
        flip and go other way with offset 5 deg.

        For Grid use Patrick Wallace's Mag 7 Tyco star grid it covers
        sky equal-area, has a bright star as target and wraps around
        both axes to better sample the encoders. Choose and load the
        grid coarseness.
        '''
        '''
        Prompt for ACCP model to be turned off
        if closed:
           If WxOk: open
        if parked:
             unpark

         pick grid star near zenith in west (no flip)
              expose 10 s
              solve
              Is there a bright object in field?
              adjust exposure if needed.
        Go to (-72.5deg HA, dec = 0),
             Expose, calibrate, save file.  Consider
             if we can real time solve or just gather.
        step 10 degrees forward untl ha is 77.5
        at 77.5 adjust target to (72.5, 0) and step
        backward.  Stop when you get to -77.5.
        park
        Launch reduction

A variant on this is cover a grid, cover a + sign shape.
IF sweep
        '''
       # ptr_utility.ModelOn = False

        self. sky_guard = True
        points = [(-2.5, 0), (-2.5, -30), (-30, 0), (-60, 0), (2.5, 75), (0.5, 45), \
                  (0.5, 0), (30, 0), (60, 0)]
        ha_deg_steps = (-72.5, -62.5, -52.5, -42.5, -32.5, -22.5, -12.5, -2.5, \
                         -7.5, -17.5, -27.5, -37.5, -47.5, -57.5, -67.5, \
                         2.5,  12.5, 22.5, 32.5, 42.5, 52.5, 62.5, 72.5, \
                         67.5, 57.5, 47.5, 37.5, 27.5, 17.5, 7.5)
        length = len(points)
        count = 0
        print("Starting cross, # of points:  ", length)
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera_1_1']['name'])
        for point_value in points:
            target_ra = ra_fix(g_dev['mnt'].mount.SiderealTime - point_value[0]/15.)
            target_dec = point_value[1]
            #     #  Go to closest Mag 7.5 Tycho * with no flip
            # focus_star = tycho.dist_sort_targets(target_ra, target_dec, \
            #                    g_dev['mnt'].mount.SiderealTime)
            # if focus_star is None:
            #     print("No near star, skipping.")   #This should not happen.
            #     continue
            #print("Going to near focus star " + str(focus_star[0]) + "  degrees away.")
            #req = {'ra':  focus_star[1][1],
            #       'dec': focus_star[1][0]     #Note order in important (dec, ra)
            req = {'ra':  target_ra,
                   'dec': target_dec     #Note order in important (dec, ra)
                   }
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            st = ''
            while g_dev['mnt'].mount.Slewing or g_dev['enc'].status['dome_slewing']:
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                if g_dev['enc'].status['dome_slewing']: st += 'd>'
                print(st)
                st = ''
                g_dev['obs'].update_status()
                time.sleep(0.5)
            time.sleep(3)
            g_dev['obs'].update_status()
            req = {'time': 30,  'alias': 'sq01', 'image_type': 'experimental'}
            opt = {'area': 150, 'count': 1, 'bin': '2,2', 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Equator Run'}
            result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            result = 'simulated result.'
            count += 1
            print('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')
        g_dev['mnt'].mount.Tracking = False
        print("Equatorial sweep completed. Happy reducing.")
        ptr_utility.ModelOn = True
        self.sky_guard = False
        return

    def sky_grid_pointing_run(self, req, opt, spacing=10, vertical=False, grid=False, alt_minimum=25):
        #camera_name = str(self.config['camera']['camera_1_1']['name'])
        '''
        unpark telescope
        if not open, open dome
        go to zenith & expose (Consider using Nearest mag 7 grid star.)
        verify reasonable transparency
            Ultimately, check focus, find a good exposure level
        go to -72.5 degrees of ha, 0  expose
        ha += 10; repeat to Ha = 67.5
        += 5, expose
        -= 10 until -67.5

        if vertical go ha = -0.25 and step dec 85 -= 10 to -30 then
        flip and go other way with offset 5 deg.

        For Grid use Patrick Wallace's Mag 7 Tyco star grid it covers
        sky equal-area, has a bright star as target and wraps around
        both axes to better sample the encoders. Choose and load the
        grid coarseness.
        '''
        '''
        Prompt for ACCP model to be turned off
        if closed:
           If WxOk: open
        if parked:
             unpark

         pick grid star near zenith in west (no flip)
              expose 10 s
              solve
              Is there a bright object in field?
              adjust exposure if needed.
        Go to (-72.5deg HA, dec = 0),
             Expose, calibrate, save file.  Consider
             if we can real time solve or just gather.
        step 10 degrees forward untl ha is 77.5
        at 77.5 adjust target to (72.5, 0) and step
        backward.  Stop when you get to -77.5.
        park
        Launch reduction

A variant on this is cover a grid, cover a + sign shape.
IF sweep
        '''
        self.sky_guard = True
        #ptr_utility.ModelOn = False
        print("Starting sky sweep. ")
        g_dev['mnt'].unpark_command({}, {})
        if g_dev['enc'].is_dome:
            g_dev['enc'].Slaved = True  #Bring the dome into the picture.
        g_dev['obs'].update_status()
        try:
            g_dev['scr'].screen_dark()
        except:
            pass
        g_dev['obs'].update_status()
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera_1_1']['name'])

        sid = g_dev['mnt'].mount.SiderealTime
        if req['gridType'] == 'medium':  # ~50
            grid = 4
        if req['gridType'] == 'coarse':  # ~30
            grid = 7
        if req['gridType'] == 'fine':    # ~100
            grid = 2

        grid_stars = tycho.az_sort_targets(sid, grid)  #4 produces about 50 targets.
        length = len(grid_stars)
        print(length, "Targets chosen for grid.")
        last_az = 0.25
        count = 0
        for grid_star in grid_stars:
            if grid_star is None:
                print("No near star, skipping.")   #This should not happen.
                count += 1
                continue
            if grid_star[0] < last_az:   #Consider also insisting on a reasonable HA, eg., >= altitude of the Pole.
               count += 1
               continue
            last_az = grid_star[0] + 0.01
            print("Going to near grid star " + str(grid_star) + " (az, (dec, ra)")
            req = {'ra':  grid_star[1][1],
                   'dec': grid_star[1][0]     #Note order is important (dec, ra)
                   }
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            time.sleep(0.5)
            st = ''
            while g_dev['mnt'].mount.Slewing or g_dev['enc'].status['dome_slewing']:
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                if g_dev['enc'].status['dome_slewing']: st += 'd>'
                print(st)
                st = ''
                g_dev['obs'].update_status()
                time.sleep(0.5)

            time.sleep(1)  #Give a little extra time for mount to settle.
            g_dev['obs'].update_status()
            req = {'time': 30,  'alias': 'sq01', 'image_type': 'experimental'}
            opt = {'area': 150, 'count': 1, 'bin': '2,2', 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Tycho grid.'}
            result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            result = 'simulated result.'
            count += 1
            print('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')

        #g_dev['mnt'].park()
        print("Equatorial sweep completed. Happy reducing.")
        ptr_utility.ModelOn = True
        self.sky_guard = False
        return

    def rel_sky_grid_pointing_run(self, req, opt, spacing=10, vertical=False, grid=False, alt_minimum=25):
        #camera_name = str(self.config['camera']['camera_1_1']['name'])
        '''
        unpark telescope
        if not open, open dome
        go to zenith & expose (Consider using Nearest mag 7 grid star.)
        verify reasonable transparency
            Ultimately, check focus, find a good exposure level
        go to -72.5 degrees of ha, 0  expose
        ha += 10; repeat to Ha = 67.5
        += 5, expose
        -= 10 until -67.5

        if vertical go ha = -0.25 and step dec 85 -= 10 to -30 then
        flip and go other way with offset 5 deg.

        For Grid use Patrick Wallace's Mag 7 Tyco star grid it covers
        sky equal-area, has a bright star as target and wraps around
        both axes to better sample the encoders. Choose and load the
        grid coarseness.
        '''
        '''
        Prompt for ACCP model to be turned off
        if closed:
           If WxOk: open
        if parked:
             unpark

         pick grid star near zenith in west (no flip)
              expose 10 s
              solve
              Is there a bright object in field?
              adjust exposure if needed.
        Go to (-72.5deg HA, dec = 0),
             Expose, calibrate, save file.  Consider
             if we can real time solve or just gather.
        step 10 degrees forward untl ha is 77.5
        at 77.5 adjust target to (72.5, 0) and step
        backward.  Stop when you get to -77.5.
        park
        Launch reduction

A variant on this is cover a grid, cover a + sign shape.
IF sweep
        '''
        #breakpoint()
        self.sky_guard = True
        ptr_utility.ModelOn = False
        print("Starting sky sweep.")
        g_dev['mnt'].unpark_command({}, {})
        if g_dev['enc'].is_dome:
            g_dev['enc'].Slaved = True  #Bring the dome into the picture.
        g_dev['obs'].update_status()
        g_dev['scr'].screen_dark()
        g_dev['obs'].update_status()
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera_1_1']['name'])

        sid = g_dev['mnt'].mount.SiderealTime
        if req['gridType'] == 'medium':  # ~50
            grid = 4
        if req['gridType'] == 'coarse':  # ~30
            grid = 7
        if req['gridType'] == 'fine':    # ~100
            grid = 2
        grid_stars = tycho.tpt_grid
        length = len(grid_stars)
        print(length, "Targets chosen for grid.")
        last_az = 0.25
        count = 0
        for grid_star in grid_stars:
            if grid_star is None:
                print("No near star, skipping.")   #This should not happen.
                count += 1
                continue
            if grid_star[0] < last_az:   #Consider also insisting on a reasonable HA
               count += 1
               continue
            last_az = grid_star[0] + 0.001
            print("Going to near grid star " + str(grid_star) + " (az, (dec, ra)")
            req = {'ra':  grid_star[1][1],
                   'dec': grid_star[1][0]     #Note order is important (dec, ra)
                   }
            opt = {}
            g_dev['mnt'].go_command(req, opt)
            time.sleep(0.5)
            st = ''
            while g_dev['mnt'].mount.Slewing or g_dev['enc'].status['dome_slewing']:
                if g_dev['mnt'].mount.Slewing: st += 'm>'
                if g_dev['enc'].status['dome_slewing']: st += 'd>'
                print(st)
                st = ''
                g_dev['obs'].update_status()
                time.sleep(0.5)

            time.sleep(3)
            g_dev['obs'].update_status()
            req = {'time': 15,  'alias': 'sq01', 'image_type': 'experimental'}
            opt = {'area': 150, 'count': 1, 'bin': '2,2', 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Tycho grid.'}
            result = g_dev['cam'].expose_command(req, opt)
            g_dev['obs'].update_status()
            result = 'simulated result.'
            count += 1
            print('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')

        g_dev['mnt'].mount.Tracking = False
        print("Equatorial sweep completed. Happy reducing.")
        ptr_utility.ModelOn = True
        self.sky_guard = False
        return

    def vertical_pointing_run(self, req, opt, spacing=10, vertical=False, grid=False, alt_minimum=25):
        '''
        unpark telescope
        if not open, open dome
        go to zenith & expose (Consider using Nearest mag 7 grid star.)
        verify reasonable transparency
            Ultimately, check focus, find a good exposure level
        go to -72.5 degrees of ha, 0  expose
        ha += 10; repeat to Ha = 67.5
        += 5, expose
        -= 10 until -67.5

        if vertical go ha = -0.25 and step dec 85 -= 10 to -30 then
        flip and go other way with offset 5 deg.

        For Grid use Patrick Wallace's Mag 7 Tyco star grid it covers
        sky equal-area, has a bright star as target and wraps around
        both axes to better sample the encoders. Choose and load the
        grid coarseness.
        '''
        '''
        Prompt for ACCP model to be turned off
        if closed:
           If WxOk: open
        if parked:
             unpark

         pick grid star near zenith in west (no flip)
              expose 10 s
              solve
              Is there a bright object in field?
              adjust exposure if needed.
        Go to (-72.5deg HA, dec = 0),
             Expose, calibrate, save file.  Consider
             if we can real time solve or just gather.
        step 10 degrees forward untl ha is 77.5
        at 77.5 adjust target to (72.5, 0) and step
        backward.  Stop when you get to -77.5.
        park
        Launch reduction

A variant on this is cover a grid, cover a + sign shape.
IF sweep
        '''
        self.sky_guard = True
        #ptr_utility.ModelOn = False
        # dec_steps = [-30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30, \
        #              35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85]
        dec_steps = [-30, -20, -10, 0, 10, 20, 30, 40, 50, 55, 60, 65, 70, 75, 80, 82.5, \
                     77.5, 72.5, 67.5, 62.5, 57.5, 50, 45, 35, 25, 15, 5, -5, -15, -25]
        # dec_copy = dec_steps[:-1].copy()
        # dec_copy.reverse()
        # dec_steps += dec_copy
        length = len(dec_steps)*2
        count = 0
        print("Starting West dec sweep, ha = 0.1")
        g_dev['mnt'].unpark_command()
        #cam_name = str(self.config['camera']['camera_1_1']['name'])
        for ha in [0.1, -0.1]:
            for degree_value in dec_steps:
                target_ra =  ra_fix(g_dev['mnt'].mount.SiderealTime - ha)


                #     #  Go to closest Mag 7.5 Tycho * with no flip
                # focus_star = tycho.dist_sort_targets(target_ra, target_dec, \
                #                    g_dev['mnt'].mount.SiderealTime)
                # if focus_star is None:
                #     print("No near star, skipping.")   #This should not happen.
                #     continue
                # print("Going to near focus star " + str(focus_star[0]) + "  degrees away.")
                req = {'ra':  target_ra,
                       'dec': degree_value}
                opt = {}
                #Should have an Alt limit check here
                g_dev['mnt'].go_command(req, opt)
                st = ''
                while g_dev['mnt'].mount.Slewing or g_dev['enc'].status['dome_slewing']:
                    if g_dev['mnt'].mount.Slewing: st += 'm>'
                    if g_dev['enc'].status['dome_slewing']: st += 'd>'
                    print(st)
                    st = ''
                    g_dev['obs'].update_status()
                    time.sleep(0.5)
                time.sleep(3)
                g_dev['obs'].update_status()
                req = {'time': 15,  'alias': 'sq01', 'image_type': 'experimental'}
                opt = {'area': 150, 'count': 1, 'bin': '2,2', 'filter': g_dev['fil'].filter_data[0][0], 'hint': 'Tycho grid.'}
                result = g_dev['cam'].expose_command(req, opt)
                g_dev['obs'].update_status()
                result = 'simulated result.'
                count += 1
                print('\n\nResult:  ', result,   'To go count:  ', length - count,  '\n\n')
                g_dev['obs'].update_status()
                result = 'simulated'
                print('Result:  ', result)
        g_dev['mnt'].stop_command()
        print("Vertical sweep completed. Happy reducing.")
        self.equitorial_pointing_run({},{})
        ptr_utility.ModelOn = True
        self.sky_guard = False
        return