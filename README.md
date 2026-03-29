# E621-Sync
Simple script for synchronization with e621.net

## Navigation 
- [Features](#features)
- [Config setup](#config-setup)
- [How to add pool](#how-to-add-pool)
- [TODO](#todo)
- [Disclaimer](#disclaimer)

## Features
- Authorization through username and [API key](https://e621.net/api_keys)
- Synchronization images from local folder and favorites
- Pools subdirectories and synchronization with content from pools
- Scheduled synchronization
- Auto-delete [blacklisted](https://e621.net/users/settings?tab=blacklist) and duplicates

## Config setup
```json
{
  "authentication": {
    "username": "Your e621.net account username",
    "api_key": "Your e621.net account API key"
  },
  "auto_delete": {
    "blacklisted": true,
    "duplicates": true 
  },
  "root_dir": "Path to local directory",
  "sync_timer": 3600 
}
```

## How to add pool
- Create empty subdirectory in your root directory
- Make file `POOL_ID.pool` in this directory (Example: `40387.pool`)
- Wait for/Start synchronization
- All images from pool will be downloaded

## TODO
- [ ] Video synchronization

### Disclaimer
*This project and its creator are not associated with Dragon Fruit Ventures LLC.*
