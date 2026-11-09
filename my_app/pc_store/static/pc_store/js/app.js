import { Actions } from './actions.js';
import { AmbientTree } from './ambient.js';
import { Navigation } from './navigation.js';
import { Player } from './player.js';

const player = new Player();
const ambient = new AmbientTree();
let actions;
const navigation = new Navigation({
    mount: () => {
        actions.mount();
        ambient.sync();
    },
    unmount: () => actions.unmount(),
});
actions = new Actions(player, navigation);
actions.mount();
