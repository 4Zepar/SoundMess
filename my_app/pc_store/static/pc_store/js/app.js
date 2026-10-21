import { Actions } from './actions.js';
import { Navigation } from './navigation.js';
import { Player } from './player.js';

const player = new Player();
let actions;
const navigation = new Navigation({
    mount: () => actions.mount(),
    unmount: () => actions.unmount(),
});
actions = new Actions(player, navigation);
actions.mount();
