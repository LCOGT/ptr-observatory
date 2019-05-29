config = {
    "site": "site4",
    "mounts": {
        "mount1": {
            "telescopes": {
                "t1": {
                    "cameras": {
                        "cam1": {
                            "type": "ccd",
                            "pixels": "2048",
                        },
                        "cam2": {
                            "type": "cmos",
                            "pixels": "8172",
                        },
                    },
                    "focusers": {
                        "foc1": {
                            "cameras": ["cam1", "cam2"]
                        }
                    }
                },
                "t2": {
                    "cameras": {}
                }
            }
            
        },
        "mount2": {
            "telescopes": {
                "t3": {
                    "cameras": {
                        "cam3": {
                            "type": "ccd",
                        }
                    }
                }
            }
        },
    }
}