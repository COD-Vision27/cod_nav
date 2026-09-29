# auto_save_map.launch.py
import os
from launch import LaunchDescription
from launch.actions import TimerAction, ExecuteProcess

def generate_launch_description():
    ld = LaunchDescription()

    def create_save_command(suffix: str) -> list:
        return [
            'bash', '-c',
            'source /opt/ros/jazzy/setup.bash && '
            'source /home/daiyuxin/cod_-rm2026_-navigation/install/setup.bash && '
            'mkdir -p /home/daiyuxin/cod_-rm2026_-navigation/src/cod_bringup/maps/auto_save && '
            f'ros2 run nav2_map_server map_saver_cli -f /home/daiyuxin/cod_-rm2026_-navigation/src/cod_bringup/maps/auto_save/auto_map_{suffix}'
        ]

    intervals = [ 30, 60, 90, 120, 150, 180, 210, 240, 270, 300]    #保存时间间隔
    for t in intervals:
        action = TimerAction(
            period=float(t),
            actions=[ExecuteProcess(cmd=create_save_command("$(date +%H%M%S)"), output='screen')]
        )
        ld.add_action(action)

    return ld