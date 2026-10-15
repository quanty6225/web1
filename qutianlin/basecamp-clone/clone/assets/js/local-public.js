import {Application} from './packages/stimulus.js';
import Count from './controllers/active_count_controller.js';
import Map from './controllers/activity_map_controller.js';
const app=Application.start();app.register('active-count',Count);app.register('activity-map',Map);
