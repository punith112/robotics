#!/usr/bin/env python
# Copyright (C) 2017 Udacity Inc.
# This file is part of Robotic Arm: Pick and Place project for Udacity
# Robotics nano-degree program
# All Rights Reserved.
# Author: Harsh Pandya

# import modules
import rospy
import tf
from kuka_arm.srv import *
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from geometry_msgs.msg import Pose
from mpmath import *
from sympy import *

# Create symbols. Define constants
# note: initializing variables outside of IK_server(). This is because setting up variables in SymPy is 'muy expensivo'
d1, d2, d3, d4, d5, d6, d7 = symbols ('d1:8') # link offset
a0, a1, a2, a3, a4, a5, a6 = symbols ('a0:7') # link length
alpha0, alpha1, alpha2, alpha3, alpha4, alpha5, alpha6 = symbols('alpha0:7') # twist angle
q1, q2, q3, q4, q5, q6, q7 = symbols ('q1:8') # joint angle symbols (theta_i)


# Create Modified DH parameters (KUKA KR210 DH Parameters)
DH_Table = { alpha0:      0, a0:      0, d1:  0.75, q1:          q1, # i = 1
             alpha1: -pi/2., a1:   0.35, d2:     0, q2: -pi/2. + q2, # i = 2
             alpha2:      0, a2:   1.25, d3:     0, q3:          q3, # i = 3
             alpha3: -pi/2., a3: -0.054, d4:   1.5, q4:          q4, # i = 4
             alpha4:  pi/2., a4:      0, d5:     0, q5:          q5, # i = 5
             alpha5: -pi/2., a5:      0, d6:     0, q6:          q6, # i = 6
             alpha6:      0, a6:      0, d7: 0.303, q7:           0} # i = 7

	    
# Define Modified DH Transformation matrix
def TF_Matrix(alpha, a, d, q):
    TF = Matrix([[           cos(q),           -sin(q),           0,           	 a],
                [ sin(q)*cos(alpha), cos(q)*cos(alpha), -sin(alpha), -sin(alpha)*d],
                [ sin(q)*sin(alpha), cos(q)*sin(alpha),  cos(alpha),  cos(alpha)*d],
                [                 0,                 0,          0,              1]])
    return TF


# Create individual transformation matrices
# note:  I'm learning through feedback that using subs() is slower than using NumPy and SciPy.  
#        subs() and evalf() are from SymPy.  They are meant to be used for simple evaluation.  
#        subs() and evalf() slow down with larger calculations (moreso than NumPy and SciPy). 
#        I'll keep the subs() function for this project and consider changing next time.  
T0_1  = TF_Matrix(alpha0, a0, d1, q1).subs(DH_Table)
T1_2  = TF_Matrix(alpha1, a1, d2, q2).subs(DH_Table)
T2_3  = TF_Matrix(alpha2, a2, d3, q3).subs(DH_Table)
T3_4  = TF_Matrix(alpha3, a3, d4, q4).subs(DH_Table)
T4_5  = TF_Matrix(alpha4, a4, d5, q5).subs(DH_Table)
T5_6  = TF_Matrix(alpha5, a5, d6, q6).subs(DH_Table)
T6_EE = TF_Matrix(alpha6, a6, d7, q7).subs(DH_Table)

# Generating a generalized homogeneous transform between base_link and gripper_link using only end-effector (gripper) pose.
T0_EE = T0_1 * T1_2 * T2_3 * T3_4 * T4_5 * T5_6 * T6_EE


# Extract rotation matrices from the transformation matrices
r, p, y = symbols('r p y')

Rot_x = Matrix([[1,      0,       0], 
                [0, cos(r), -sin(r)],
                [0, sin(r), cos(r)]])  # ROLL

Rot_y = Matrix([[cos(p),  0, sin(p)],
                [0,       1,      0],
                [-sin(p), 0, cos(p)]]) # Pitch

Rot_z = Matrix([[cos(y), -sin(y), 0],
                [sin(y),  cos(y), 0],
                [     0,       0, 1]]) # yaw


# Gripper values
Rot_Gripper_x = Rot_x(r)
Rot_Gripper_y = Rot_y(p)
Rot_Gripper_z = Rot_z(y)

# Rotation matrix of end effector (Gripper)
Rot_EE = Rot_Gripper_z * Rot_Gripper_y * Rot_Gripper_x

# Setting up the end effector correction matrix (rotation correction)
Rot_correction = Rot_z(180 * pi/180) * Rot_y(-90 * pi/180)

# Finalizing the adjustment for the discrepancy between the DH table and the URDF reference frame
Rot_EE = Rot_EE * Rot_correction
# note: Rot_EE will be used in the code below when capturing the WC (wrist center)


def handle_calculate_IK(req):
    rospy.loginfo("Received %s eef-poses from the plan" % len(req.poses))
    if len(req.poses) < 1:
        print "No valid poses received"
        return -1
    else:
        # Initialize service response
        joint_trajectory_list = []
        for x in xrange(0, len(req.poses)):
            # IK code starts here
            joint_trajectory_point = JointTrajectoryPoint()

	    # Extract end-effector position and orientation from request
	    # px,py,pz = end-effector position
	    # roll, pitch, yaw = end-effector orientation
            px = req.poses[x].position.x
            py = req.poses[x].position.y
            pz = req.poses[x].position.z

            (roll, pitch, yaw) = tf.transformations.euler_from_quaternion(
                [req.poses[x].orientation.x, req.poses[x].orientation.y,
                    req.poses[x].orientation.z, req.poses[x].orientation.w])

    	### Your IK code here
        # Compensate for rotation discrepancy between DH parameters and Gazebo
        # Operation needed to adjust the discrepancy between the DH table and the URDF reference frame vs DH convention
        
        EE = Matrix([px, py, pz])
        ROT_EE = ROT_EE.subs({'r': roll, 'p': pitch, 'y': yaw})
        WC = EE - (0.303) * ROT_EE[:,2] # DH_Table[d7] = 0.303
	    
	    
        # Theta 1, 2, 3
        # Calculate joint angles using Geometric IK method
        theta1 = atan2(WC[1], WC[0])  # theta1 = atan2(y,x)

        # SSS triangle for theta 2 and theta 3
        side_a = 1.501 # DH_Table[d4]
        side_b = sqrt(pow((sqrt(WC[0] * WC[0] + WC[1] * WC[1]) - 0.35), 2) + pow((WC[2] - 0.75), 2))
        side_c = 1.25 # DH_Table[a2]

        angle_a = acos((side_b * side_b + side_c * side_c - side_a * side_a) / (2 * side_b * side_c))
        angle_b = acos((side_a * side_a + side_c * side_c - side_b * side_b) / (2 * side_a * side_c))
        angle_c = acos((side_a * side_a + side_b * side_b - side_c * side_c) / (2 * side_a * side_b))

        theta2 = pi/2 - angle_a - atan2(WC[2] - 0.75, sqrt(WC[0] * WC[0] + WC[1] * WC[1]) - 0.35)
        theta3 = pi/2 - (angle_b + 0.036)  # 0.036 accounts for sag on link4 of -0.054m

        # Get the rotation from joint 3 to the end effector (joint 0 to joint 3)
        # We now have the the theta for these joints that define the pose of the wrist center
        R0_3 = T0_1[0:3,0:3] * T1_2[0:3,0:3] * T2_3[0:3,0:3]
        R0_3_eval = R0_3.evalf(subs={q1 : theta1, q2 : theta2, q3 : theta3})
        R3_6 = R0_3_eval.transpose() * ROT_EE


        # Theta 4, 5, 6
        # Euler angles from rotation matrix
        theta4 = atan2(R3_6[2,2], -R3_6[0,2])
        theta5 = atan2(sqrt(R3_6[0,2] * R3_6[0,2] + R3_6[2,2] * R3_6[2,2]), R3_6[1,2])
        theta6 = atan2(-R3_6[1,1], R3_6[1,0])

        # Populate response for the IK request
        # In the next line replace theta1,theta2...,theta6 by your joint angle variables
        joint_trajectory_point.positions = [theta1, theta2, theta3, theta4, theta5, theta6]
        joint_trajectory_list.append(joint_trajectory_point)

        rospy.loginfo("length of Joint Trajectory List: %s" % len(joint_trajectory_list))
        return CalculateIKResponse(joint_trajectory_list)


def IK_server():
    # initialize node and declare calculate_ik service
    rospy.init_node('IK_server')
    s = rospy.Service('calculate_ik', CalculateIK, handle_calculate_IK)
    print "Ready to receive an IK request"
    rospy.spin()

if __name__ == "__main__":
    IK_server()
