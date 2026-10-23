<?php
if ( isset( $_SERVER['REQUEST_URI'] ) &&
     ( strpos( $_SERVER['REQUEST_URI'], '/wp-json/' ) !== false ||
       strpos( $_SERVER['REQUEST_URI'], 'rest_route=' ) !== false ) ) {
    $_SERVER['HTTPS'] = 'on';
}