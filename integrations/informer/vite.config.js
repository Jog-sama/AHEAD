import {defineConfig} from 'vite';
import informer from '@entrinsik/vite-plugin-informer';
export default defineConfig({base:'./',plugins:[informer()]});
